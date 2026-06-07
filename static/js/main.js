// Auto-cerrar flash messages
document.querySelectorAll('.flash').forEach(el => {
  setTimeout(() => { el.style.transition = 'opacity .5s'; el.style.opacity = '0'; setTimeout(() => el.remove(), 500); }, 4000);
});
