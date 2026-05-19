"""SLO calculator package.

Public surface:

    from runbooks.lib.slo.catalog import load as load_catalog, SloDef
    from runbooks.lib.slo.clients import PromClient, EsClient, HactlClient
    from runbooks.lib.slo.calc    import compute, SloSnapshot
    from runbooks.lib.slo.writer  import SloWriter

`runbooks/slo-check.py` is the thin CLI that wires these together.
"""
