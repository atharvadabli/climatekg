# Evaluation implementation note

The first complete pass produced answers for 28 questions. `XPG012` and `XPG027`
stopped after query planning because Nominatim was unavailable and
`NominatimGeocoder.resolve()` allowed the transport exception to abort the query.

The surrounding query implementation already expected geocoding failures to be
reported through `last_failure_reason` and converted into a
`SPATIAL_GAZETTEER_FAILED` warning. The geocoder did not implement that contract.

The evaluation branch adds the smallest corresponding fix:

- catch network and operating-system transport failures at the geocoder boundary;
- record the exception type and message in `last_failure_reason`;
- return unresolved geometry;
- do not cache a transient failure;
- allow the existing query warning and unresolved-spatial-support logic to run.

No coordinates, Context values, Claims, scores, or fallback evidence are invented.
After this change both questions completed and preserved the gazetteer failure in their
query warnings.
