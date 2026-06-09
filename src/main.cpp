#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <OneWire.h>
#include <DallasTemperature.h>
#include <TM1637Display.h>
#include <ESPmDNS.h>
#include <WiFiUdp.h>
#include <ArduinoOTA.h>

// ================= CONFIGURACION DE RED =================

// 1. Fallback defensivo por si falla la inyección de PlatformIO o falta el secrets.ini
#ifndef WIFI_SSID
  #pragma message "WARNING: WIFI_SSID no definido en build_flags. Usando fallback."
  #define WIFI_SSID "SSID_POR_DEFECTO"
  #define WIFI_PASS "PASS_POR_DEFECTO"
  #define MQTT_SERVER "127.0.0.1"
#endif

// 2. Asignación limpia consumiendo las macros
const char* ssid = WIFI_SSID;
const char* password = WIFI_PASS;
const char* mqtt_server = MQTT_SERVER;
const int mqtt_port = 1883;

// ================= HARDWARE Y PINES =====================
const int PIN_ONE_WIRE = 4;
const int PIN_RELE_FRIO = 26; // Active-LOW
const int PIN_CLK = 18;       // TM1637 Clock
const int PIN_DIO = 19;       // TM1637 Data

// Direcciones MAC de los DS18B20
DeviceAddress addrMosto = { 0x28, 0xFF, 0xB0, 0x96, 0x51, 0x16, 0x04, 0x18 };
DeviceAddress addrAmbiente = { 0x28, 0xFF, 0x6A, 0x47, 0x55, 0x16, 0x03, 0x68 };

// ================= VARIABLES DE CONTROL =================
float tempMosto = 0.0;
float tempAmbiente = 0.0;
float setpoint = 18.0;     // Valor de seguridad inicial (Fail-safe)
float histeresis = 0.3;    // Corta a 17.7°C, arranca a 18.3°C

bool releEstado = false;   // false = Apagado, true = Encendido
unsigned long lastRelayToggle = 0;
const unsigned long MIN_OFF_TIME = 300000; // Anti-Short Cycle: 5 min (300,000 ms)

unsigned long lastMqttMsg = 0;
unsigned long lastMqttReconnectAttempt = 0; // Para reconexión asíncrona
const unsigned long MQTT_INTERVAL = 10000;  // Telemetría cada 10 seg

// ================= INSTANCIAS ===========================
WiFiClient espClient;
PubSubClient client(espClient);
OneWire oneWire(PIN_ONE_WIRE);
DallasTemperature sensors(&oneWire);
TM1637Display display(PIN_CLK, PIN_DIO);

// ================= CONFIGURACION VISUAL =================
const uint8_t SEG_ERR[] = { SEG_G, SEG_G, SEG_G, SEG_G };
const uint8_t SEG_DEGREE = SEG_A | SEG_B | SEG_F | SEG_G;

// ================= FUNCIONES ============================

void setup_wifi() {
  delay(10);
  Serial.printf("\nConectando a %s...\n", ssid);
  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.printf("\nWiFi conectado. IP: %s\n", WiFi.localIP().toString().c_str());
}

void setupOTA() {
  ArduinoOTA.setHostname("esp32-fermentador");
  ArduinoOTA.setPassword("FierroOTA2026");

  ArduinoOTA.onStart([]() {
    String type = (ArduinoOTA.getCommand() == U_FLASH) ? "sketch" : "filesystem";
    Serial.println("Iniciando actualizacion OTA: " + type);
  });
  
  ArduinoOTA.onEnd([]() {
    Serial.println("\nActualizacion finalizada exitosamente. Reiniciando...");
  });
  
  ArduinoOTA.onProgress([](unsigned int progress, unsigned int total) {
    Serial.printf("Progreso: %u%%\r", (progress / (total / 100)));
  });
  
  ArduinoOTA.onError([](ota_error_t error) {
    Serial.printf("Error fatal [%u]: ", error);
    if (error == OTA_AUTH_ERROR) Serial.println("Fallo de Autenticacion");
    else if (error == OTA_BEGIN_ERROR) Serial.println("Fallo al Iniciar");
    else if (error == OTA_CONNECT_ERROR) Serial.println("Fallo de Conexion");
    else if (error == OTA_RECEIVE_ERROR) Serial.println("Fallo de Recepcion");
    else if (error == OTA_END_ERROR) Serial.println("Fallo al Finalizar");
  });

  ArduinoOTA.begin();
}

void callback(char* topic, byte* payload, unsigned int length) {
  // 1. Convertir el payload crudo en un String sanitizado
  String messageTemp = "";
  for (int i = 0; i < length; i++) {
    // Ignorar saltos de línea y retornos de carro que pueda meter Node-RED
    if ((char)payload[i] != '\n' && (char)payload[i] != '\r') {
      messageTemp += (char)payload[i];
    }
  }

  // 2. Comprobar tópico y actualizar
  if (String(topic) == "birra/setpoint") {
    float nuevoSetpoint = messageTemp.toFloat();
    
    // 3. Log de Diagnóstico (Vital)
    Serial.print("MQTT IN -> Payload Crudo: [");
    Serial.print(messageTemp);
    Serial.print("] | Parseado: ");
    Serial.println(nuevoSetpoint);

    // 4. Validación de Sanidad
    if(nuevoSetpoint > 0.0 && nuevoSetpoint < 30.0) { 
      setpoint = nuevoSetpoint;
      Serial.printf("SYS: Setpoint actualizado a %.2f C\n", setpoint);
    } else {
      Serial.println("ERR: Setpoint ignorado (fuera de rango o invalido)");
    }
  }
}

// Reescrito para no bloquear el procesador
boolean reconnect() {
  Serial.print("Intentando conexión MQTT...");
  String clientId = "Fermentador-Edge-";
  clientId += String(random(0xffff), HEX);
  
  // Asumiendo que definas ACLs en el futuro, acá pondrías usuario y password
  if (client.connect(clientId.c_str())) {
    Serial.println("Conectado al broker.");
    client.subscribe("birra/setpoint");
    return true;
  } else {
    Serial.print("Fallo, rc=");
    Serial.println(client.state());
    return false;
  }
}

void controlTermico() {
  unsigned long now = millis();

  // Fail-Safe: Falla el sensor sumergible
  if (tempMosto == DEVICE_DISCONNECTED_C || tempMosto < -5.0) {
    digitalWrite(PIN_RELE_FRIO, HIGH); // Forzar apagado
    releEstado = false;
    display.setSegments(SEG_ERR);
    return;
  }

  // --- Actualizar Display TM1637 ---
  int tempInt = (int)(tempMosto * 10); 
  uint8_t data[] = { 0, 0, 0, 0 };
  
  int digito1 = (tempInt / 100) % 10;
  int digito2 = (tempInt / 10) % 10;  
  int digito3 = tempInt % 10;         

  if (tempInt >= 100) {
    data[0] = display.encodeDigit(digito1);
  } else {
    data[0] = 0x00;
  }
  
  data[1] = display.encodeDigit(digito2) | 0x80; 
  data[2] = display.encodeDigit(digito3);
  data[3] = SEG_DEGREE; 

  display.setSegments(data);

  // --- Lazo Termostato ---
  if (tempMosto > (setpoint + histeresis)) {
    if (!releEstado && (now - lastRelayToggle >= MIN_OFF_TIME || lastRelayToggle == 0)) {
      digitalWrite(PIN_RELE_FRIO, LOW);
      releEstado = true;
      lastRelayToggle = now;
      Serial.println("SYS: Compresor ON");
    }
  } else if (tempMosto <= (setpoint - histeresis)) {
    if (releEstado) {
      digitalWrite(PIN_RELE_FRIO, HIGH);
      releEstado = false;
      lastRelayToggle = now;
      Serial.println("SYS: Compresor OFF");
    }
  }
}

void setup() {
  Serial.begin(115200);
  
  pinMode(PIN_RELE_FRIO, OUTPUT);
  digitalWrite(PIN_RELE_FRIO, HIGH); 

  display.setBrightness(0x0a);
  display.clear();

  sensors.begin();
  sensors.setResolution(addrMosto, 11);
  sensors.setResolution(addrAmbiente, 11);

  setup_wifi();
  
  // Iniciar servicio OTA para quedar a la escucha
  setupOTA();
  
  client.setServer(mqtt_server, mqtt_port);
  client.setCallback(callback);
}

void loop() {
  // 1. Capa de Administración: Siempre viva
  ArduinoOTA.handle(); 

  // 2. Capa de Transporte: Manejo asíncrono de caídas de red
  if (!client.connected()) {
    unsigned long now = millis();
    if (now - lastMqttReconnectAttempt > 5000) {
      lastMqttReconnectAttempt = now;
      // Intenta reconectar; si falla, sale de inmediato
      if (reconnect()) {
        lastMqttReconnectAttempt = 0;
      }
    }
  } else {
    client.loop(); 
  }

  // 3. Capa de Negocio: Control de hardware independiente de la red
  unsigned long now = millis();
  if (now - lastMqttMsg > MQTT_INTERVAL) {
    lastMqttMsg = now;
    
    sensors.requestTemperatures();
    tempMosto = sensors.getTempC(addrMosto);
    tempAmbiente = sensors.getTempC(addrAmbiente);
    
    controlTermico();

    if (client.connected()) {
      char payload[150];
      snprintf(payload, sizeof(payload), 
               "{\"mosto\": %.2f, \"ambiente\": %.2f, \"rele\": %d, \"setpoint\": %.2f}", 
               tempMosto, tempAmbiente, releEstado ? 1 : 0, setpoint);
               
      client.publish("birra/telemetria", payload);
      Serial.printf("MQTT OUT: %s\n", payload);
    }
  }
}