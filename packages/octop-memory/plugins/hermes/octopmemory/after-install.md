# Activate OctopMemory

Run `hermes memory setup` and select `octopmemory`, then `hermes gateway restart`.
Verify loading with `hermes memory status` and search a phrase from a test conversation using
`hermes octopmemory search "Python" -n 5 --corpus all`.

If dependencies fail to install, install `octop-memory[cli]` into Hermes' actual Python interpreter.
The native plugin does not include `octopmemory.installer`.
See the [shared integration guide](https://github.com/TencentCloud/octop-memory/blob/main/docs/integrations.md#hermes).
