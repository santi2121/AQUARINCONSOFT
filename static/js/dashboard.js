(function () {
  const root = document.documentElement;
  const savedTheme = localStorage.getItem("aquarincon-theme") || "dark";
  root.setAttribute("data-theme", savedTheme);
  document.body.setAttribute("data-theme", savedTheme);

  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
      root.setAttribute("data-theme", next);
      document.body.setAttribute("data-theme", next);
      localStorage.setItem("aquarincon-theme", next);
      showToast(next === "dark" ? "Modo oscuro activado" : "Modo claro activado", "info");
    });
  });

  const trigger = document.querySelector("[data-profile-trigger]");
  const menu = document.querySelector("[data-profile-menu]");
  if (trigger && menu) {
    trigger.addEventListener("click", () => menu.classList.toggle("open"));
    document.addEventListener("click", (event) => {
      if (!menu.contains(event.target) && !trigger.contains(event.target)) {
        menu.classList.remove("open");
      }
    });
  }

  function showToast(message, type) {
    let stack = document.querySelector(".toast-stack");
    if (!stack) {
      stack = document.createElement("div");
      stack.className = "toast-stack";
      document.body.appendChild(stack);
    }
    const toast = document.createElement("div");
    toast.className = `toast toast-${type || "info"}`;
    toast.textContent = message;
    stack.appendChild(toast);
    setTimeout(() => {
      toast.classList.add("hide");
      setTimeout(() => toast.remove(), 260);
    }, 4200);
  }
  window.showAquaToast = showToast;

  document.querySelectorAll(".flash").forEach((flash) => {
    const type = Array.from(flash.classList).find((item) => item.startsWith("flash-"));
    showToast(flash.textContent.trim(), type ? type.replace("flash-", "") : "info");
    flash.style.display = "none";
  });

  const adminMap = document.getElementById("adminPointMap");
  const userMap = document.getElementById("userPaymentMap");

  function loadGoogleMaps(key, callback) {
    if (!key) return false;
    if (window.google && window.google.maps) {
      callback();
      return true;
    }
    const callbackName = `initAquaMap${Date.now()}`;
    window[callbackName] = callback;
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(key)}&callback=${callbackName}`;
    script.async = true;
    script.defer = true;
    document.head.appendChild(script);
    return true;
  }

  function fallbackMap(el, text) {
    if (!el) return;
    el.innerHTML = `<div class="map-fallback">${text}</div>`;
  }

  if (adminMap) {
    const key = adminMap.dataset.googleKey;
    const latInput = document.querySelector("[data-lat-input]");
    const lngInput = document.querySelector("[data-lng-input]");
    const start = {
      lat: parseFloat(latInput.value) || 4.0300,
      lng: parseFloat(lngInput.value) || -74.9700,
    };
    const ready = loadGoogleMaps(key, () => {
      const map = new google.maps.Map(adminMap, { center: start, zoom: 15 });
      const marker = new google.maps.Marker({ position: start, map, draggable: true });
      marker.addListener("dragend", () => {
        const pos = marker.getPosition();
        latInput.value = pos.lat().toFixed(7);
        lngInput.value = pos.lng().toFixed(7);
      });
      map.addListener("click", (event) => {
        marker.setPosition(event.latLng);
        latInput.value = event.latLng.lat().toFixed(7);
        lngInput.value = event.latLng.lng().toFixed(7);
      });
    });
    if (!ready) adminMap.hidden = true;
  }

  if (userMap) {
    const key = userMap.dataset.googleKey;
    const points = JSON.parse(userMap.dataset.mapPoints || "[]").filter((point) => point.latitud && point.longitud);
    const ready = loadGoogleMaps(key, () => {
      const center = points.length ? { lat: Number(points[0].latitud), lng: Number(points[0].longitud) } : { lat: 4.0300, lng: -74.9700 };
      const map = new google.maps.Map(userMap, { center, zoom: points.length > 1 ? 13 : 15 });
      points.forEach((point) => {
        const marker = new google.maps.Marker({
          position: { lat: Number(point.latitud), lng: Number(point.longitud) },
          map,
          title: point.nombre,
        });
        const info = new google.maps.InfoWindow({
          content: `<strong>${point.nombre}</strong><br>${point.direccion}<br><a target="_blank" href="https://www.google.com/maps/dir/?api=1&destination=${point.latitud},${point.longitud}">Abrir ruta</a>`,
        });
        marker.addListener("click", () => info.open({ anchor: marker, map }));
      });
    });
    if (!ready) userMap.hidden = true;
  }
})();
