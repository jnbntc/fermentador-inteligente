from(bucket: "telemetria_birra")
  |> range(start: v.timeRangeStart, stop: v.timeRangeStop)
  |> filter(fn: (r) => r._measurement == "fermentador")
  |> filter(fn: (r) => int(v: v.timeRangeStop) - int(v: r._time) <= 900000000000)
  |> filter(fn: (r) => r._field == "mosto_valid" or r._field == "ambiente_valid" or r._field == "wifi" or r._field == "mqtt" or r._field == "relay")
  |> map(fn: (r) => ({r with _value: string(v: r._value)}))
  |> group(columns: ["_field"])
  |> last()
  |> map(fn: (r) => ({r with
      Señal: if r._field == "mosto_valid" then "Sonda MOSTO" else if r._field == "ambiente_valid" then "Sonda AMBIENTE" else if r._field == "wifi" then "Wi-Fi (último informe)" else if r._field == "mqtt" then "MQTT (último informe)" else "Salida del relé",
      Estado: if r._field == "relay" then (if r._value == "true" then "Encendida" else "Apagada") else if r._field == "mosto_valid" or r._field == "ambiente_valid" then (if r._value == "true" then "Válida" else "Inválida") else (if r._value == "true" then "Conectado" else "Desconectado")
  }))
  |> group()
  |> sort(columns: ["Señal"])
