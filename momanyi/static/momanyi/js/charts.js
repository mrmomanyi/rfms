// Draws the charts on the dashboards from the data the view puts in #chart-data.
(function () {
    'use strict';

    var dataElement = document.getElementById('chart-data');
    if (!dataElement || typeof Chart === 'undefined') return;
    var data = JSON.parse(dataElement.textContent);

    var GREEN = '#15803d';
    var GREEN_SOFT = 'rgba(21, 128, 61, 0.15)';
    var PALETTE = ['#166534', '#15803d', '#22c55e', '#86efac', '#0d9488', '#2563eb', '#d97706', '#9ca3af'];

    function canvas(id) {
        var el = document.getElementById(id);
        return el ? el.getContext('2d') : null;
    }

    function tooltipUnit(unit) {
        return {
            callbacks: {
                label: function (ctx) {
                    var value = ctx.parsed.y !== undefined ? ctx.parsed.y : ctx.parsed;
                    return ' ' + Number(value).toLocaleString() + ' ' + unit;
                }
            }
        };
    }

    function bar(id, block, label, unit) {
        var ctx = canvas(id);
        if (!ctx || !block || !block.labels.length) return;
        new Chart(ctx, {
            type: 'bar',
            data: {
                labels: block.labels,
                datasets: [{ label: label, data: block.values, backgroundColor: PALETTE, borderRadius: 6 }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: tooltipUnit(unit) },
                scales: {
                    y: { beginAtZero: true, title: { display: true, text: unit } },
                    x: { grid: { display: false } }
                }
            }
        });
    }

    function line(id, block, label, unit) {
        var ctx = canvas(id);
        if (!ctx || !block || !block.labels.length) return;
        new Chart(ctx, {
            type: 'line',
            data: {
                labels: block.labels,
                datasets: [{
                    label: label, data: block.values, borderColor: GREEN, backgroundColor: GREEN_SOFT,
                    fill: true, tension: 0.35, pointRadius: 4, pointBackgroundColor: GREEN
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { display: false }, tooltip: tooltipUnit(unit) },
                scales: { y: { beginAtZero: true, title: { display: true, text: unit } } }
            }
        });
    }

    function doughnut(id, block, unit) {
        var ctx = canvas(id);
        if (!ctx || !block) return;
        var total = block.values.reduce(function (a, b) { return a + b; }, 0);
        if (!total) return;
        new Chart(ctx, {
            type: 'doughnut',
            data: {
                labels: block.labels,
                datasets: [{ data: block.values, backgroundColor: ['#15803d', '#9ca3af'], borderWidth: 2 }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: false,
                plugins: { legend: { position: 'bottom' }, tooltip: tooltipUnit(unit) }
            }
        });
    }

    bar('chart-species', data.species, 'CO2e stored', 'tonnes CO\u2082e');
    line('chart-forecast', data.forecast, 'Planted trees: CO2e stored', 'tonnes CO\u2082e');
    doughnut('chart-split', data.split, 'tonnes CO\u2082e');
    bar('chart-oxygen-species', data.oxygen_species, 'Oxygen', 'tonnes O\u2082');
})();
