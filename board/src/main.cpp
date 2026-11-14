#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <DHTesp.h>
#include "secrets.h"


const char* ssid = "Wokwi-GUEST";
const char* password = "";

// Replace with your VM's API URL for readings
const char* serverUrl = "http://psalms-365.chilecentral.cloudapp.azure.com/readings";

DHTesp dht;
const int DHT_PIN = 15; // Change if your diagram.json uses a different pin

unsigned long lastMillis = 0;
const long interval = 10000; // 10 seconds

void setup() {
  Serial.begin(115200);
  delay(2000);

  // Connect to Wi-Fi
  WiFi.begin(ssid, password);
  Serial.print("Connecting to WiFi");
  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nConnected!");
  
  // Print MAC address so you can register it via POST /fans first!
  Serial.print("MAC Address: ");
  Serial.println(WiFi.macAddress());

  dht.setup(DHT_PIN, DHTesp::DHT22);
  delay(2000);
}

void loop() {
  unsigned long currentMillis = millis();
  if (currentMillis - lastMillis >= interval) {
    lastMillis = currentMillis;

    if (WiFi.status() == WL_CONNECTED) {
      float humidity = dht.getHumidity();
      
      if (isnan(humidity)) {
        Serial.println("Failed to read from DHT sensor!");
        return;
      }

      String mac = WiFi.macAddress();
      
      HTTPClient http;
      http.begin(serverUrl);
      http.addHeader("Content-Type", "application/json");
      http.addHeader("X-API-Key", DEVICE_KEY);

      // Construct JSON payload
      String jsonPayload = "{\"mac\":\"" + mac + "\",\"humidity\":" + String(humidity, 2) + "}";

      Serial.print("Sending humidity: ");
      Serial.println(jsonPayload);

      int httpResponseCode = http.POST(jsonPayload);

      if (httpResponseCode > 0) {
        String response = http.getString();
        Serial.print("Response Code: ");
        Serial.println(httpResponseCode);
        Serial.println(response);
      } else {
        Serial.print("Error code: ");
        Serial.println(httpResponseCode);
      }

      http.end();
    } else {
      Serial.println("WiFi Disconnected");
    }
  }}

  #define DEVICE_KEY "your_api_key_here"

