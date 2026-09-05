# Frontend library

`api.ts` provides the typed, bounded browser request layer used by the mission
list and detail workspace. Side-effectful workflow requests are never retried
automatically; after an uncertain POST failure the UI requires a status refresh.
