#!/usr/bin/env python3
"""
Analyze Longhorn CIFS backups to identify unused volumes and calculate space usage.
"""
import json
import subprocess
import sys
from datetime import datetime
from collections import defaultdict

def get_kubectl_json(resource, namespace):
    """Get Kubernetes resource as JSON."""
    result = subprocess.run(
        ['kubectl', 'get', resource, '-n', namespace, '-o', 'json'],
        capture_output=True,
        text=True,
        check=True
    )
    return json.loads(result.stdout)

def normalize_volume_name(name):
    """Normalize volume name for comparison."""
    # Remove hash suffixes from backup volume names
    # e.g., "absenty-development-data-729a43b2" -> "absenty-development-data"
    if '-' in name and name.count('-') > 2:
        parts = name.split('-')
        # Check if last part looks like a hash (hex string)
        if len(parts[-1]) == 8 and all(c in '0123456789abcdef' for c in parts[-1].lower()):
            return '-'.join(parts[:-1])
    return name

def main():
    print("Fetching data from cluster...")
    
    # Get current volumes
    volumes_data = get_kubectl_json('volumes', 'storage')
    current_volumes = {v['metadata']['name'] for v in volumes_data.get('items', [])}
    
    # Get backup volumes
    bv_data = get_kubectl_json('backupvolumes', 'storage')
    backup_volumes = {}
    for bv in bv_data.get('items', []):
        name = bv['metadata']['name']
        normalized = normalize_volume_name(name)
        backup_volumes[name] = {
            'normalized': normalized,
            'last_backup': bv.get('status', {}).get('lastBackupAt', ''),
            'last_backup_name': bv.get('status', {}).get('lastBackupName', '')
        }
    
    # Get backups
    backups_data = get_kubectl_json('backups', 'storage')
    backups = backups_data.get('items', [])
    
    # Match backups to volumes
    backup_by_volume = defaultdict(list)
    backup_sizes = {}
    
    for backup in backups:
        backup_name = backup['metadata']['name']
        volume_name = backup.get('spec', {}).get('volumeName', '')
        size = int(backup.get('status', {}).get('size', 0))
        created = backup.get('status', {}).get('createdAt', '')
        
        backup_sizes[backup_name] = size
        
        # Try to find volume name
        if not volume_name:
            # Match via backup volume's last backup name
            for bv_name, bv_info in backup_volumes.items():
                if bv_info['last_backup_name'] == backup_name:
                    volume_name = bv_name
                    break
        
        if volume_name:
            backup_by_volume[volume_name].append({
                'name': backup_name,
                'size': size,
                'created': created
            })
    
    # Calculate space usage per volume
    volume_sizes = defaultdict(int)
    total_size = 0
    
    for backup in backups:
        size = int(backup.get('status', {}).get('size', 0))
        total_size += size
        
        volume_name = backup.get('spec', {}).get('volumeName', '')
        if not volume_name:
            backup_name = backup['metadata']['name']
            for bv_name, bv_info in backup_volumes.items():
                if bv_info['last_backup_name'] == backup_name:
                    volume_name = bv_name
                    break
        
        if volume_name:
            volume_sizes[volume_name] += size
    
    # Find unused volumes
    unused_volumes = []
    for bv_name, bv_info in backup_volumes.items():
        normalized = bv_info['normalized']
        matched = False
        
        # Check if matches any current volume
        for cv in current_volumes:
            if cv == normalized or cv == bv_name:
                matched = True
                break
            # Check for UUID-based PVCs
            if bv_name.startswith('pvc-') and cv.startswith('pvc-'):
                # Compare UUID parts
                bv_parts = bv_name.split('-')
                cv_parts = cv.split('-')
                if len(bv_parts) >= 5 and len(cv_parts) >= 5:
                    if bv_parts[1:5] == cv_parts[1:5]:
                        matched = True
                        break
        
        if not matched:
            unused_volumes.append(bv_name)
    
    # Generate report
    print("\n" + "=" * 80)
    print("LONGHORN CIFS BACKUP ANALYSIS REPORT")
    print("=" * 80)
    print(f"\nGenerated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"\nBackup Target: cifs://192.168.31.230/backups")
    print(f"\nCurrent Active Volumes: {len(current_volumes)}")
    print(f"Backup Volumes Found: {len(backup_volumes)}")
    print(f"Total Backups: {len(backups)}")
    print(f"Total Backup Size: {total_size / (1024**3):.2f} GB")
    
    print("\n" + "=" * 80)
    print("UNUSED VOLUMES IN BACKUP (Not in Current Cluster)")
    print("=" * 80)
    
    unused_total = 0
    unused_details = []
    
    for uv in sorted(unused_volumes):
        size = volume_sizes.get(uv, 0)
        unused_total += size
        last_backup = backup_volumes[uv]['last_backup']
        backup_count = len(backup_by_volume.get(uv, []))
        unused_details.append({
            'name': uv,
            'size': size,
            'last_backup': last_backup,
            'backup_count': backup_count
        })
    
    if unused_details:
        for detail in sorted(unused_details, key=lambda x: x['size'], reverse=True):
            print(f"\n{detail['name']}")
            print(f"  Size: {detail['size'] / (1024**3):.2f} GB")
            print(f"  Last Backup: {detail['last_backup']}")
            print(f"  Backup Count: {detail['backup_count']}")
    else:
        print("\nNo unused volumes found!")
    
    print(f"\nTotal Unused Volume Backup Size: {unused_total / (1024**3):.2f} GB")
    
    print("\n" + "=" * 80)
    print("SPACE USAGE BY VOLUME (Top 30)")
    print("=" * 80)
    
    sorted_volumes = sorted(volume_sizes.items(), key=lambda x: x[1], reverse=True)[:30]
    for vol_name, size in sorted_volumes:
        # Check if active
        is_active = False
        normalized = normalize_volume_name(vol_name)
        for cv in current_volumes:
            if cv == vol_name or cv == normalized:
                is_active = True
                break
            if vol_name.startswith('pvc-') and cv.startswith('pvc-'):
                vol_parts = vol_name.split('-')
                cv_parts = cv.split('-')
                if len(vol_parts) >= 5 and len(cv_parts) >= 5:
                    if vol_parts[1:5] == cv_parts[1:5]:
                        is_active = True
                        break
        
        status = "ACTIVE" if is_active else "UNUSED"
        print(f"{vol_name[:55]:55s} {size / (1024**3):10.2f} GB [{status}]")
    
    print("\n" + "=" * 80)
    print("SYSTEM BACKUPS")
    print("=" * 80)
    system_backups = [b for b in backups if b['metadata']['name'].startswith('system-backup-')]
    system_total = sum(int(b.get('status', {}).get('size', 0)) for b in system_backups)
    print(f"System Backup Count: {len(system_backups)}")
    print(f"System Backup Total Size: {system_total / (1024**3):.2f} GB")
    
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    active_total = sum(size for vol_name, size in volume_sizes.items() 
                      if any(cv == vol_name or cv == normalize_volume_name(vol_name) 
                            for cv in current_volumes))
    print(f"Active Volume Backup Size: {active_total / (1024**3):.2f} GB")
    print(f"Unused Volume Backup Size: {unused_total / (1024**3):.2f} GB")
    print(f"System Backup Size: {system_total / (1024**3):.2f} GB")
    print(f"Total Backup Size: {total_size / (1024**3):.2f} GB")
    
    if unused_total > 0:
        print(f"\n⚠️  Potential space savings: {unused_total / (1024**3):.2f} GB")
        print("   Consider cleaning up unused volume backups if no longer needed.")

if __name__ == '__main__':
    main()
