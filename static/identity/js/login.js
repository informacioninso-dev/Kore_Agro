document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.querySelector("[data-password-toggle]");
  const password = document.getElementById("id_password");
  if (!toggle || !password) return;

  toggle.addEventListener("click", () => {
    const visible = password.type === "text";
    password.type = visible ? "password" : "text";
    toggle.textContent = visible ? "Ver" : "Ocultar";
    toggle.setAttribute("aria-label", visible ? "Mostrar contraseña" : "Ocultar contraseña");
  });
});
