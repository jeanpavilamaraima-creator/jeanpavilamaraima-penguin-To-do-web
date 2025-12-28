document.addEventListener('DOMContentLoaded', () => {
    const themeSwitch = document.getElementById('themeSwitch');
    const body = document.body;
    const themeLabel = document.getElementById('themeLabel');

    // Cargar preferencia guardada
    const savedTheme = localStorage.getItem('theme') || 'light';
    if (savedTheme === 'dark') {
        enableDarkMode();
    }

    themeSwitch.addEventListener('change', () => {
        if (themeSwitch.checked) {
            enableDarkMode();
        } else {
            disableDarkMode();
        }
    });

    function enableDarkMode() {
        body.classList.add('bg-dark', 'text-white');
        body.classList.remove('bg-light');
        
        // Ajustar cards y tablas
        document.querySelectorAll('.card').forEach(c => c.classList.add('text-bg-dark'));
        document.querySelectorAll('.table').forEach(t => t.classList.add('table-dark'));

        themeLabel.textContent = 'Modo Oscuro';
        themeSwitch.checked = true;
        localStorage.setItem('theme', 'dark');
    }

    function disableDarkMode() {
        body.classList.add('bg-light');
        body.classList.remove('bg-dark', 'text-white');
        
        document.querySelectorAll('.card').forEach(c => c.classList.remove('text-bg-dark'));
        document.querySelectorAll('.table').forEach(t => t.classList.remove('table-dark'));

        themeLabel.textContent = 'Modo Claro';
        themeSwitch.checked = false;
        localStorage.setItem('theme', 'light');
    }
});