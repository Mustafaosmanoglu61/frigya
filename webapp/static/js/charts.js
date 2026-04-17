/* Frigya — Chart.js helpers */

const GREEN = 'rgba(40, 167, 69, 0.8)';
const RED   = 'rgba(220, 53, 69, 0.8)';
const BLUE  = 'rgba(31, 78, 121, 0.85)';
const BLUE_LINE = 'rgba(46, 117, 182, 1)';

function barColors(values) {
  return values.map(v => v >= 0 ? GREEN : RED);
}

function initMonthlyChart(canvasId, labels, values) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Aylık K/Z (USD)',
        data: values,
        backgroundColor: barColors(values),
        borderRadius: 4,
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => '$' + ctx.parsed.y.toLocaleString('en-US', {minimumFractionDigits: 2})
          }
        }
      },
      scales: {
        y: {
          ticks: {
            callback: v => '$' + v.toLocaleString('en-US')
          }
        }
      }
    }
  });
}

function initCumulativeChart(canvasId, labels, values) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  const lastVal = values.length ? values[values.length - 1] : 0;
  new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Kümülatif K/Z (USD)',
        data: values,
        borderColor: lastVal >= 0 ? BLUE_LINE : 'rgba(220,53,69,1)',
        backgroundColor: lastVal >= 0 ? 'rgba(46,117,182,0.08)' : 'rgba(220,53,69,0.08)',
        fill: true,
        tension: 0.35,
        pointRadius: 3,
        pointHoverRadius: 5,
      }]
    },
    options: {
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => '$' + ctx.parsed.y.toLocaleString('en-US', {minimumFractionDigits: 2})
          }
        }
      },
      scales: {
        y: {
          ticks: {
            callback: v => '$' + v.toLocaleString('en-US')
          }
        }
      }
    }
  });
}

function initSymbolChart(canvasId, labels, values) {
  const ctx = document.getElementById(canvasId);
  if (!ctx) return;
  new Chart(ctx, {
    type: 'bar',
    data: {
      labels,
      datasets: [{
        label: 'Net K/Z (USD)',
        data: values,
        backgroundColor: barColors(values),
        borderRadius: 3,
      }]
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: ctx => '$' + ctx.parsed.x.toLocaleString('en-US', {minimumFractionDigits: 2})
          }
        }
      },
      scales: {
        x: {
          ticks: {
            callback: v => '$' + v.toLocaleString('en-US')
          }
        }
      }
    }
  });
}
