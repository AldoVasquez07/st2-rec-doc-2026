// Notificaciones push (RF-0013)
self.addEventListener('push', (event) => {
  let d = {titulo: 'AgroPredix', texto: '', url: '/'};
  try { d = Object.assign(d, event.data.json()); } catch (_) {}
  event.waitUntil(self.registration.showNotification(d.titulo, {
    body: d.texto, icon: '{% static "pwa/icon-192.png" %}', data: {url: d.url}}));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(clients.openWindow((event.notification.data && event.notification.data.url) || '/'));
});