#!/usr/bin/env python3
"""
Delete all unused dynamic volume backups (UUID-based PVCs) that are not active.
"""
import json
import subprocess
import sys

def get_kubectl_json(resource, namespace):
    """Get Kubernetes resource as JSON."""
    result = subprocess.run(
        ['kubectl', 'get', resource, '-n', namespace, '-o', 'json'],
        capture_output=True,
        text=True,
        check=True
    )
    return json.loads(result.stdout)

def main():
    print("Fetching data from cluster...")
    
    # Get active volumes
    volumes_data = get_kubectl_json('volumes', 'storage')
    active_volumes = {v['metadata']['name'] for v in volumes_data.get('items', [])}
    
    # Get backup volumes
    bv_data = get_kubectl_json('backupvolumes', 'storage')
    
    # Find dynamic volume backups (UUID-based PVCs) that are not active
    dynamic_unused = []
    for bv in bv_data.get('items', []):
        name = bv['metadata']['name']
        # Check if it's a dynamic volume (starts with pvc- and has UUID pattern)
        if name.startswith('pvc-') and len(name.split('-')) >= 5:
            # Check if it matches any active volume
            is_active = False
            for av in active_volumes:
                # Match UUID parts (first 4 parts after pvc-)
                if av.startswith('pvc-'):
                    av_parts = av.split('-')
                    bv_parts = name.split('-')
                    if len(av_parts) >= 5 and len(bv_parts) >= 5:
                        if av_parts[1:5] == bv_parts[1:5]:
                            is_active = True
                            break
                # Also check if name matches exactly
                if av == name or name.startswith(av) or av.startswith(name):
                    is_active = True
                    break
            
            if not is_active:
                dynamic_unused.append(name)
    
    if not dynamic_unused:
        print("No unused dynamic volume backups found.")
        return
    
    print(f"\nFound {len(dynamic_unused)} unused dynamic volume backups to delete")
    print("=" * 80)
    
    # Ask for confirmation
    print("\nVolumes to be deleted:")
    for i, bv_name in enumerate(dynamic_unused[:10], 1):
        print(f"  {i}. {bv_name}")
    if len(dynamic_unused) > 10:
        print(f"  ... and {len(dynamic_unused) - 10} more")
    
    # Delete them
    print(f"\nDeleting {len(dynamic_unused)} unused dynamic volume backups...")
    print("=" * 80)
    
    deleted = []
    failed = []
    
    for bv_name in dynamic_unused:
        try:
            result = subprocess.run(
                ['kubectl', 'delete', 'backupvolume', bv_name, '-n', 'storage'],
                capture_output=True,
                text=True,
                timeout=30
            )
            if result.returncode == 0:
                deleted.append(bv_name)
                print(f"✅ Deleted: {bv_name}")
            else:
                error_msg = result.stderr.strip()[:100] if result.stderr else result.stdout.strip()[:100]
                failed.append((bv_name, error_msg))
                print(f"❌ Failed: {bv_name} - {error_msg}")
        except subprocess.TimeoutExpired:
            failed.append((bv_name, "Timeout"))
            print(f"❌ Timeout deleting: {bv_name}")
        except Exception as e:
            failed.append((bv_name, str(e)))
            print(f"❌ Error deleting {bv_name}: {e}")
    
    print(f"\n{'=' * 80}")
    print("Summary:")
    print(f"  Successfully deleted: {len(deleted)}")
    print(f"  Failed: {len(failed)}")
    
    if failed:
        print("\nFailed deletions:")
        for bv_name, error in failed:
            print(f"  - {bv_name}: {error}")

if __name__ == '__main__':
    main()
