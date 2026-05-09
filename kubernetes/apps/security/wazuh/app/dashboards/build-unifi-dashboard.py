#!/usr/bin/env python3
"""Build OpenSearch Dashboards saved-objects NDJSON for the UniFi Wazuh dashboard."""

import json
import sys

INDEX_PATTERN = "wazuh-alerts-*"
INDEX_PATTERN_ID = "wazuh-alerts-*"   # OSD uses the title as the id by default
DECODER_FILTER = {
    "match_phrase": {"decoder.name": "unifi"}
}

def search_source(extra_filter=None):
    """Build the searchSourceJSON wrapper. Always filters decoder.name:unifi."""
    src = {
        "index": INDEX_PATTERN_ID,
        "query": {"language": "kuery", "query": "decoder.name : \"unifi\""},
        "filter": []
    }
    return json.dumps(src)


def viz(vis_id, title, vis_state):
    """Build a visualization saved-object."""
    return {
        "id": vis_id,
        "type": "visualization",
        "namespaces": ["default"],
        "attributes": {
            "title": title,
            "visState": json.dumps(vis_state),
            "uiStateJSON": "{}",
            "description": "",
            "version": 1,
            "kibanaSavedObjectMeta": {
                "searchSourceJSON": search_source(),
            },
        },
        "references": [
            {"id": INDEX_PATTERN_ID, "name": "kibanaSavedObjectMeta.searchSourceJSON.index", "type": "index-pattern"}
        ],
    }


def vis_metric_count(vis_id, title):
    return viz(vis_id, title, {
        "title": title,
        "type": "metric",
        "params": {
            "addTooltip": True,
            "addLegend": False,
            "type": "metric",
            "metric": {
                "percentageMode": False,
                "useRanges": False,
                "colorSchema": "Green to Red",
                "metricColorMode": "None",
                "colorsRange": [{"from": 0, "to": 10000}],
                "labels": {"show": True},
                "invertColors": False,
                "style": {"bgFill": "#000", "bgColor": False, "labelColor": False, "subText": "",
                          "fontSize": 60},
            }
        },
        "aggs": [
            {"id": "1", "enabled": True, "type": "count", "schema": "metric", "params": {"customLabel": "UniFi Events"}}
        ],
    })


def vis_line_timeline(vis_id, title):
    return viz(vis_id, title, {
        "title": title,
        "type": "line",
        "params": {
            "type": "line",
            "grid": {"categoryLines": False},
            "categoryAxes": [{"id": "CategoryAxis-1", "type": "category", "position": "bottom", "show": True,
                              "style": {}, "scale": {"type": "linear"}, "labels": {"show": True, "filter": True, "truncate": 100},
                              "title": {}}],
            "valueAxes": [{"id": "ValueAxis-1", "name": "LeftAxis-1", "type": "value", "position": "left", "show": True,
                           "style": {}, "scale": {"type": "linear", "mode": "normal"}, "labels": {"show": True, "rotate": 0, "filter": False, "truncate": 100},
                           "title": {"text": "Count"}}],
            "seriesParams": [{"show": True, "type": "line", "mode": "normal", "data": {"label": "Count", "id": "1"},
                              "valueAxis": "ValueAxis-1", "drawLinesBetweenPoints": True, "lineWidth": 2,
                              "showCircles": True, "interpolate": "linear"}],
            "addTooltip": True,
            "addLegend": True,
            "legendPosition": "right",
            "times": [],
            "addTimeMarker": False,
            "labels": {},
            "thresholdLine": {"show": False, "value": 10, "width": 1, "style": "full", "color": "#E7664C"}
        },
        "aggs": [
            {"id": "1", "enabled": True, "type": "count", "schema": "metric", "params": {}},
            {"id": "2", "enabled": True, "type": "date_histogram", "schema": "segment",
             "params": {"field": "@timestamp", "useNormalizedEsInterval": True, "scaleMetricValues": False,
                        "interval": "auto", "drop_partials": False, "min_doc_count": 1, "extended_bounds": {}}}
        ],
    })


def vis_terms_horizontal(vis_id, title, field, size=10):
    return viz(vis_id, title, {
        "title": title,
        "type": "horizontal_bar",
        "params": {
            "type": "histogram",
            "grid": {"categoryLines": False},
            "categoryAxes": [{"id": "CategoryAxis-1", "type": "category", "position": "left", "show": True,
                              "style": {}, "scale": {"type": "linear"}, "labels": {"show": True, "rotate": 0, "filter": False, "truncate": 200},
                              "title": {}}],
            "valueAxes": [{"id": "ValueAxis-1", "name": "BottomAxis-1", "type": "value", "position": "bottom", "show": True,
                           "style": {}, "scale": {"type": "linear", "mode": "normal"}, "labels": {"show": True, "rotate": 75, "filter": True, "truncate": 100},
                           "title": {"text": "Count"}}],
            "seriesParams": [{"show": True, "type": "histogram", "mode": "normal", "data": {"label": "Count", "id": "1"},
                              "valueAxis": "ValueAxis-1", "drawLinesBetweenPoints": True, "lineWidth": 2,
                              "showCircles": True}],
            "addTooltip": True,
            "addLegend": False,
            "legendPosition": "right",
            "times": [],
            "addTimeMarker": False,
            "labels": {"show": True}
        },
        "aggs": [
            {"id": "1", "enabled": True, "type": "count", "schema": "metric", "params": {}},
            {"id": "2", "enabled": True, "type": "terms", "schema": "segment",
             "params": {"field": field, "size": size, "order": "desc", "orderBy": "1", "otherBucket": False, "missingBucket": False}}
        ],
    })


def vis_pie(vis_id, title, field, size=10):
    return viz(vis_id, title, {
        "title": title,
        "type": "pie",
        "params": {
            "type": "pie",
            "addTooltip": True,
            "addLegend": True,
            "legendPosition": "right",
            "isDonut": True,
            "labels": {"show": False, "values": True, "last_level": True, "truncate": 100}
        },
        "aggs": [
            {"id": "1", "enabled": True, "type": "count", "schema": "metric", "params": {}},
            {"id": "2", "enabled": True, "type": "terms", "schema": "segment",
             "params": {"field": field, "size": size, "order": "desc", "orderBy": "1", "otherBucket": True, "missingBucket": False}}
        ],
    })


def vis_data_table(vis_id, title):
    return viz(vis_id, title, {
        "title": title,
        "type": "table",
        "params": {
            "perPage": 25,
            "showPartialRows": False,
            "showMetricsAtAllLevels": False,
            "sort": {"columnIndex": None, "direction": None},
            "showTotal": False,
            "totalFunc": "sum",
            "percentageCol": ""
        },
        "aggs": [
            {"id": "1", "enabled": True, "type": "count", "schema": "metric", "params": {}},
            {"id": "2", "enabled": True, "type": "terms", "schema": "bucket",
             "params": {"field": "rule.description", "size": 25, "order": "desc", "orderBy": "1", "otherBucket": False, "missingBucket": False, "customLabel": "Rule"}},
            {"id": "3", "enabled": True, "type": "terms", "schema": "bucket",
             "params": {"field": "data.uni_changeagent", "size": 5, "order": "desc", "orderBy": "1", "otherBucket": False, "missingBucket": False, "customLabel": "Admin"}},
            {"id": "4", "enabled": True, "type": "terms", "schema": "bucket",
             "params": {"field": "data.uni_devname", "size": 5, "order": "desc", "orderBy": "1", "otherBucket": False, "missingBucket": False, "customLabel": "Device"}}
        ],
    })


# ─── Build the dashboard panel layout ──────────────────────────────────────
panels = [
    {"version": "2.19.5", "panelIndex": "1", "gridData": {"x": 0,  "y": 0,  "w": 12, "h": 6,  "i": "1"}, "embeddableConfig": {}, "panelRefName": "panel_0"},   # Count metric
    {"version": "2.19.5", "panelIndex": "2", "gridData": {"x": 12, "y": 0,  "w": 36, "h": 6,  "i": "2"}, "embeddableConfig": {}, "panelRefName": "panel_1"},   # Timeline
    {"version": "2.19.5", "panelIndex": "3", "gridData": {"x": 0,  "y": 6,  "w": 24, "h": 12, "i": "3"}, "embeddableConfig": {}, "panelRefName": "panel_2"},   # Top rules
    {"version": "2.19.5", "panelIndex": "4", "gridData": {"x": 24, "y": 6,  "w": 24, "h": 12, "i": "4"}, "embeddableConfig": {}, "panelRefName": "panel_3"},   # Top admins
    {"version": "2.19.5", "panelIndex": "5", "gridData": {"x": 0,  "y": 18, "w": 24, "h": 10, "i": "5"}, "embeddableConfig": {}, "panelRefName": "panel_4"},   # Top devices
    {"version": "2.19.5", "panelIndex": "6", "gridData": {"x": 24, "y": 18, "w": 24, "h": 10, "i": "6"}, "embeddableConfig": {}, "panelRefName": "panel_5"},   # Rule groups
    {"version": "2.19.5", "panelIndex": "7", "gridData": {"x": 0,  "y": 28, "w": 48, "h": 14, "i": "7"}, "embeddableConfig": {}, "panelRefName": "panel_6"},   # Recent events
]

dashboard = {
    "id": "unifi-dashboard",
    "type": "dashboard",
    "namespaces": ["default"],
    "attributes": {
        "title": "UniFi - Security Events",
        "hits": 0,
        "description": "Wazuh dashboard for UniFi gateway events ingested via syslog/CEF (decoder.name:unifi). Auto-filters all panels to UniFi events; use the time picker to scope.",
        "panelsJSON": json.dumps(panels),
        "optionsJSON": json.dumps({"hidePanelTitles": False, "useMargins": True}),
        "version": 1,
        "timeRestore": True,
        "timeTo": "now",
        "timeFrom": "now-7d",
        "refreshInterval": {"pause": True, "value": 0},
        "kibanaSavedObjectMeta": {
            "searchSourceJSON": json.dumps({
                "query": {"language": "kuery", "query": "decoder.name : \"unifi\""},
                "filter": []
            })
        },
    },
    "references": [
        {"id": "unifi-events-count",       "name": "panel_0", "type": "visualization"},
        {"id": "unifi-events-timeline",    "name": "panel_1", "type": "visualization"},
        {"id": "unifi-top-rules",          "name": "panel_2", "type": "visualization"},
        {"id": "unifi-top-admins",         "name": "panel_3", "type": "visualization"},
        {"id": "unifi-top-devices",        "name": "panel_4", "type": "visualization"},
        {"id": "unifi-rule-groups",        "name": "panel_5", "type": "visualization"},
        {"id": "unifi-recent-events",      "name": "panel_6", "type": "visualization"},
    ],
}

# ─── Emit NDJSON ───────────────────────────────────────────────────────────
objects = [
    vis_metric_count("unifi-events-count", "UniFi - Total Events"),
    vis_line_timeline("unifi-events-timeline", "UniFi - Events Over Time"),
    vis_terms_horizontal("unifi-top-rules", "UniFi - Top Rules", "rule.description", size=10),
    vis_terms_horizontal("unifi-top-admins", "UniFi - Top Admins", "data.uni_changeagent", size=10),
    vis_pie("unifi-top-devices", "UniFi - Devices", "data.uni_devname", size=10),
    vis_pie("unifi-rule-groups", "UniFi - Rule Groups", "rule.groups", size=10),
    vis_data_table("unifi-recent-events", "UniFi - Recent Events Breakdown"),
    dashboard,
]

for o in objects:
    print(json.dumps(o, separators=(",", ":")))

# Final summary line (OSD imports also expect this trailing line; it's optional but harmless)
print(json.dumps({"exportedCount": len(objects), "missingRefCount": 0, "missingReferences": []}))
