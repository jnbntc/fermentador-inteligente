from(bucket: "telemetria_birra")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "fermentador")
  |> filter(fn: (r) => int(v: v.timeRangeStop) - int(v: r._time) <= 900000000000)
  |> filter(fn: (r) => r._field == "uptime_s" or r._field == "message_seq" or r._field == "control_cycles" or r._field == "control_max_gap_ms" or r._field == "hysteresis" or r._field == "lockout_remaining_s")
  |> group(columns: ["_field"])
  |> last()
  |> map(fn: (r) => ({
      Indicador: if r._field == "uptime_s" then "Tiempo encendido (s)" else if r._field == "message_seq" then "Secuencia MQTT" else if r._field == "control_cycles" then "Ciclos de control" else if r._field == "control_max_gap_ms" then "Intervalo máximo del control (ms)" else if r._field == "hysteresis" then "Histéresis (°C)" else "Protección restante (s)",
      Valor: float(v: r._value)
  }))
  |> group()
  |> sort(columns: ["Indicador"])
