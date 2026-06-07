const container = document.getElementById('container');

document.getElementById('signUp').addEventListener('click', () => {
  container.classList.add('right-panel-active');
});

document.getElementById('signIn').addEventListener('click', () => {
  container.classList.remove('right-panel-active');
});

document.querySelectorAll('.flash').forEach((flash) => {
  setTimeout(() => {
    flash.classList.add('hide');
    setTimeout(() => flash.remove(), 260);
  }, 4200);
});

document.querySelectorAll('.toggle-pw').forEach((btn) => {
  btn.addEventListener('click', () => {
    const input = btn.closest('.password-field').querySelector('input');
    const isPassword = input.type === 'password';
    input.type = isPassword ? 'text' : 'password';
    btn.querySelector('.eye-icon').style.display = isPassword ? 'none' : '';
    btn.querySelector('.eye-off-icon').style.display = isPassword ? '' : 'none';
    btn.setAttribute('aria-label', isPassword ? 'Ocultar contraseña' : 'Mostrar contraseña');
  });
});

// ── Live password requirements for registration ──
const pwInput = document.getElementById('reg-password');
const pwReqs = document.getElementById('reg-password-reqs');
const confirmInput = document.getElementById('reg-confirm-password');
const matchMsg = document.getElementById('reg-password-match');

function updateMatch() {
  if (!confirmInput || !matchMsg) return;
  const v = pwInput ? pwInput.value : '';
  const cv = confirmInput.value;
  if (cv.length === 0) {
    matchMsg.className = '';
    matchMsg.innerHTML = '● Las contraseñas deben coincidir';
  } else if (v === cv) {
    matchMsg.className = 'text-success';
    matchMsg.innerHTML = '✓ Las contraseñas coinciden';
  } else {
    matchMsg.className = '';
    matchMsg.innerHTML = '● Las contraseñas no coinciden';
  }
}

if (pwInput && pwReqs) {
  pwInput.addEventListener('input', () => {
    const v = pwInput.value;
    const checks = {
      length: v.length >= 10,
      upper: /[A-Z]/.test(v),
      lower: /[a-z]/.test(v),
      digit: /\d/.test(v),
      symbol: /[^A-Za-z0-9]/.test(v),
    };
    pwReqs.querySelectorAll('[data-req]').forEach((el) => {
      const key = el.getAttribute('data-req');
      if (checks[key]) {
        el.className = 'text-success';
        el.innerHTML = '&#10003; ' + el.textContent.replace(/^.\s*/, '');
      } else {
        el.className = '';
        el.innerHTML = '&#9679; ' + el.textContent.replace(/^.\s*/, '');
      }
    });
    updateMatch();
  });
}

if (confirmInput) {
  confirmInput.addEventListener('input', updateMatch);
}

// ── Data consent checkbox ──
const consentBox = document.getElementById('reg-consent');
const regSubmit = document.getElementById('reg-submit');
if (consentBox && regSubmit) {
  consentBox.addEventListener('change', function () {
    regSubmit.disabled = !this.checked;
    sessionStorage.setItem('reg_data_consent', this.checked ? '1' : '');
  });
  regSubmit.closest('form').addEventListener('submit', function (e) {
    if (!consentBox.checked) {
      e.preventDefault();
    }
  });
}

// ── Persist registration form data in sessionStorage ──
(function () {
  var REG_KEYS = ['nombres', 'apellidos', 'telefono', 'email', 'password', 'confirm_password'];

  REG_KEYS.forEach(function (name) {
    var el = document.querySelector('[name="' + name + '"]');
    if (el) {
      el.addEventListener('input', function () {
        sessionStorage.setItem('reg_' + name, el.value);
      });
    }
  });

  // Clear saved data when the form is submitted
  var regForm = document.querySelector('.sign-up-container form');
  if (regForm) {
    regForm.addEventListener('submit', function () {
      REG_KEYS.forEach(function (name) {
        sessionStorage.removeItem('reg_' + name);
      });
      sessionStorage.removeItem('reg_data_consent');
    });
  }

  document.addEventListener('DOMContentLoaded', function () {
    var hasData = false;

    REG_KEYS.forEach(function (name) {
      var val = sessionStorage.getItem('reg_' + name);
      if (val) {
        var el = document.querySelector('[name="' + name + '"]');
        if (el) { el.value = val; hasData = true; }
      }
    });

    if (consentBox) {
      var savedConsent = sessionStorage.getItem('reg_data_consent');
      if (savedConsent === '1') {
        consentBox.checked = true;
        regSubmit.disabled = false;
        hasData = true;
      }
    }

    if (hasData) {
      container.classList.add('right-panel-active');
    }
  });
})();
