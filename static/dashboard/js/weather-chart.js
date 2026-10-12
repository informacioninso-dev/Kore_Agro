document.addEventListener("DOMContentLoaded", () => {
  const canvas = document.getElementById("weatherChart");
  const payload = document.getElementById("weather-chart-data");
  if (!canvas || !payload || !window.Chart) return;

  const forecast = JSON.parse(payload.textContent);
  Chart.defaults.font.family = '"Atkinson Hyperlegible", "Segoe UI", Arial, sans-serif';
  const dateFormatter = new Intl.DateTimeFormat("es-EC", {
    weekday: "short",
    day: "2-digit"
  });
  const labels = forecast.dates.map((value) =>
    dateFormatter.format(new Date(`${value}T12:00:00`))
  );
  const number = (value, digits = 1) =>
    value === null || value === undefined
      ? "-"
      : Number(value).toLocaleString("es-EC", {
          minimumFractionDigits: digits,
          maximumFractionDigits: digits
        });

  new Chart(canvas, {
    data: {
      labels,
      datasets: [
        {
          type: "bar",
          label: "Lluvia (mm)",
          data: forecast.rain_mm,
          backgroundColor: "rgba(57, 121, 149, 0.28)",
          borderColor: "#397995",
          borderWidth: 1,
          borderRadius: 4,
          yAxisID: "rain",
          order: 3
        },
        {
          type: "line",
          label: "Maxima (C)",
          data: forecast.temperature_max,
          borderColor: "#b56b2b",
          backgroundColor: "#b56b2b",
          borderWidth: 2.5,
          pointRadius: 3,
          pointHoverRadius: 5,
          tension: 0.28,
          yAxisID: "temperature",
          order: 1
        },
        {
          type: "line",
          label: "Minima (C)",
          data: forecast.temperature_min,
          borderColor: "#2f6b42",
          backgroundColor: "#2f6b42",
          borderWidth: 2.5,
          pointRadius: 3,
          pointHoverRadius: 5,
          tension: 0.28,
          yAxisID: "temperature",
          order: 2
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      animation: { duration: 350 },
      plugins: {
        legend: { display: false },
        tooltip: {
          backgroundColor: "#193326",
          padding: 12,
          titleFont: { size: 13, weight: "bold" },
          bodyFont: { size: 12 },
          callbacks: {
            afterBody(items) {
              const index = items[0].dataIndex;
              return [
                `Condicion: ${forecast.conditions[index]}`,
                `Prob. lluvia: ${number(forecast.rain_probability[index], 0)} %`,
                `Viento: ${number(forecast.wind_max[index])} km/h`,
                `ET0: ${number(forecast.evapotranspiration[index], 2)} mm`,
                `UV: ${number(forecast.uv_max[index])}`
              ];
            }
          }
        }
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: "#68766a" } },
        temperature: {
          position: "left",
          grid: { color: "rgba(104, 118, 106, 0.14)" },
          ticks: { color: "#68766a", callback: (value) => `${value} C` }
        },
        rain: {
          position: "right",
          beginAtZero: true,
          grid: { drawOnChartArea: false },
          ticks: { color: "#397995", callback: (value) => `${value} mm` }
        }
      }
    }
  });
});
