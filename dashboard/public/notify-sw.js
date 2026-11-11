/* Dashboard system notifications.
   Chrome does not display `new Notification()` from a background tab.
   `registration.showNotification()` does, including while this tab is hidden.

   Dev registers this file directly. Production importScripts it into sw.js.
   skipWaiting here would override the production worker's update prompt,
   so it only runs when this file is the worker itself.
*/

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  const path =
    event.notification.data && typeof event.notification.data.path === "string"
      ? event.notification.data.path
      : "/";
  const target = new URL(path, self.location.origin).href;
  event.waitUntil(
    self.clients
      .matchAll({ type: "window", includeUncontrolled: true })
      .then(async (windowClients) => {
        const client = windowClients.find((item) =>
          item.url.startsWith(self.location.origin),
        );
        if (client) {
          await client.focus();
          client.postMessage({ type: "octop-notify-open", path });
          return;
        }
        if (self.clients.openWindow) await self.clients.openWindow(target);
      }),
  );
});

if ((self.location.pathname || "").endsWith("/notify-sw.js")) {
  self.addEventListener("install", () => {
    self.skipWaiting();
  });
  self.addEventListener("activate", (event) => {
    event.waitUntil(self.clients.claim());
  });
}
