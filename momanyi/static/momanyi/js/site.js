// Sidebar toggle for small screens
document.addEventListener('DOMContentLoaded', function () {
    var button = document.getElementById('nav-toggle');
    var sidebar = document.getElementById('sidebar');
    if (!button || !sidebar) return;
    button.addEventListener('click', function () {
        var open = sidebar.classList.toggle('open');
        button.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
});
