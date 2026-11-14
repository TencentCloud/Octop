# Magpie

Magpie is an OpenAI-compatible provider. Octop discovers it on the **server that runs Octop**, reads its model catalog, and attributes chat requests to this install and to the current thread. Magpie's own subscription routing stays inside Magpie. Octop keeps using the existing AUTO failover.

## Local one-click add

1. Open **Settings → Models** with the `providers` permission.
2. If Magpie is listening on `http://127.0.0.1:3425` on the Octop host, the page shows its version and **Add Magpie**.
3. Confirming that button reads `GET /v1/models` with the local key `magpie-octop` and creates a provider named `Magpie` only when the catalog contains chat models.
4. The configuration panel stays open. Pick models there, then set a preferred model with the existing global model control. Octop does not choose a route group for you.
5. Adding again does not overwrite an existing `Magpie` provider. Use **Check again** to repeat discovery. Discovery does not scan arbitrary URLs.

If Magpie is not running, the page stays usable. Add the Magpie preset manually or use a custom provider.

## Custom address, port, and Docker

The address is reached by the Octop process, not by the browser.

| Deployment | What to enter |
| --- | --- |
| Magpie and Octop on the same host | `http://127.0.0.1:3425/v1`. The local key `magpie-octop` is filled in only for this address. |
| Another port on that host | Start from the Magpie preset and change the base URL, or create a custom provider whose name or address identifies Magpie. Enter a real gateway key if the address is not the default above. |
| Octop inside Docker, Magpie on the host | `127.0.0.1` inside the container is the container. Publish Magpie's port into the container network, or point the base URL at the host gateway (for example `http://host.docker.internal:3425/v1` on Docker Desktop). |
| Magpie on another machine | Use the reachable base URL and a real Magpie gateway key. Do not send `magpie-octop` to a remote gateway. |

Saving from the Magpie preset stores `integration: "magpie"` so a renamed remote address is still recognized. A name that merely contains the word "magpie" is not enough.

## Refresh

On a saved Magpie provider, **Refresh models** loads the catalog and shows models that would be added or removed. Confirming applies that list with the existing provider update, which clears pins that pointed at removed models. A failed fetch or a cancelled confirmation leaves the saved list unchanged. An empty catalog asks you to confirm removing every model.

Existing models keep their enabled flag, capability edits, and group access. Newly discovered models are added disabled.

## AUTO and a pinned model

- **AUTO**, and Magpie cannot be reached: after the usual retries and failure classification, Octop can switch to another enabled chat model the caller may use, when that model fits the turn's modality and context size. The Magpie provider row is not rewritten. When Magpie recovers, the existing health cooldown applies.
- **A model you selected explicitly**: Octop reports the failure and does not switch providers.
- **No compatible candidate**: Octop returns the existing error.

Chat, IM, cron, and team turns send `X-Magpie-Session` with that turn's thread id. Octop also sends `User-Agent: Octop/<version>` unless you set your own User-Agent on the provider. Model-list and hello probes do not use a real chat thread.

## What this release does not include

Quota and routing dashboards, and a Magpie Agents page, are later work. They are not part of this provider setup.
