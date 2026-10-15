"""
Populate → Verify → Lock: LOS fields filled by the system and verified by people.

    registry.py    the field registry (config/los_fields.yaml): domains, policies, resolvers
    model.py       FieldValue records: merge (single writer), verify actions, queue, stats
    resolvers.py   resolvers that turn engine / document output into field proposals
    population.py  the population graph: resolvers in parallel → critic → proposals
"""
