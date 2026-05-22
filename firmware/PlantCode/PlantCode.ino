#include "Arduino.h"
#include "Audio.h"
#include "WiFi.h"
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <Wire.h>
#include <Adafruit_BME280.h>
#include <BH1750.h>
#include "SPIFFS.h"

// PINS
#define I2S_LRC  17
#define I2S_BCLK 16
#define I2S_DOUT 4
#define TRIG_PIN 18
#define ECHO_PIN 5
#define SOIL_PIN 32
#define SDA_PIN 21
#define SCL_PIN 22

// WIFI
String ssid     = "aalto open";
String password = "";
String serverUrl   = "https://dtap-demo1.onrender.com";
String readingsUrl = serverUrl + "/api/readings/";
String voiceUrl    = serverUrl + "/api/plant/voice/";
String deviceId    = "POT-12345";

#define WIFI_TIMEOUT_MS 10000
#define WIFI_RECOVER_MS 30000

// SENSORS
Adafruit_BME280 bme;
BH1750 lightMeter;

// AUDIO
Audio audio;
bool audioReady   = false;

// TIMING
unsigned long startTimeForRequest = 0;

// WIFI
void ensureWiFi() {
    if (WiFi.status() == WL_CONNECTED) return;

    Serial.println("WiFi lost — reconnecting...");
    WiFi.disconnect(true);
    WiFi.begin(ssid.c_str(), password.c_str());

    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - start > WIFI_TIMEOUT_MS) {
            Serial.println("WiFi reconnect timed out. Retrying...");
            WiFi.disconnect(true);
            delay(WIFI_RECOVER_MS);
            WiFi.begin(ssid.c_str(), password.c_str());
            start = millis();
        }
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nWiFi reconnected. IP: " + WiFi.localIP().toString());
}

// ---------------- DOWNLOAD AUDIO TO SPIFFS ----------------
void downloadAudio() {
    Serial.println("Downloading audio to SPIFFS...");
    audioReady = false;

    WiFiClientSecure client;
    client.setInsecure();
    client.setTimeout(15);

    HTTPClient http;
    http.begin(client, voiceUrl.c_str());
    http.setReuse(false);
    http.useHTTP10(true);
    http.setTimeout(15000);

    int code = http.GET();
    if (code != 200) {
        Serial.println("Audio download failed: " + String(code));
        http.end();
        return;
    }

    File f = SPIFFS.open("/voice.mp3", FILE_WRITE);
    if (!f) {
        Serial.println("Failed to open SPIFFS file for writing");
        http.end();
        return;
    }

    WiFiClient* stream = http.getStreamPtr();
    uint8_t buf[512];
    int total = 0;
    while (http.connected()) {
        int available = stream->available();
        if (available > 0) {
            int bytes = stream->readBytes(buf, min(available, (int)sizeof(buf)));
            f.write(buf, bytes);
            total += bytes;
        } else if (!http.connected()) {
            break;
        }
        delay(1);
    }

    f.close();
    http.end();

    if (total > 0) {
        Serial.println("Audio cached: " + String(total) + " bytes");
        audioReady = true;
    } else {
        Serial.println("Audio download got 0 bytes, will retry");
        SPIFFS.remove("/voice.mp3");
    }
}

// AUDIO CALLBACKS
void audio_info(const char* info) {
    Serial.println(info);
}
void audio_eof_mp3(const char* info) {
    Serial.println("Audio finished");
    SPIFFS.remove("/voice.mp3");
    downloadAudio();
}

// ULTRASONIC
float getDistance() {
    digitalWrite(TRIG_PIN, LOW);
    delay(60);
    digitalWrite(TRIG_PIN, HIGH);
    delay(60);
    digitalWrite(TRIG_PIN, LOW);
    long duration = pulseIn(ECHO_PIN, HIGH, 30000);
    return duration * 0.034 / 2;
}

// SETUP
void setup() {
    Serial.begin(115200);
    pinMode(TRIG_PIN, OUTPUT);
    pinMode(ECHO_PIN, INPUT);

    Wire.begin(SDA_PIN, SCL_PIN);

    if (!bme.begin(0x76)) {
        Serial.println("BME280 not found!");
    }
    lightMeter.begin();

    WiFi.begin(ssid.c_str(), password.c_str());
    Serial.print("Connecting to WiFi");
    while (WiFi.status() != WL_CONNECTED) {
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nWiFi connected. IP: " + WiFi.localIP().toString());

    // NTP sync for valid TLS
    configTime(0, 0, "pool.ntp.org", "time.nist.gov");
    Serial.print("Waiting for NTP time sync");
    time_t now = time(nullptr);
    while (now < 8 * 3600 * 2) {
        delay(500);
        Serial.print(".");
        now = time(nullptr);
    }
    Serial.println("\nTime synced");

    // Mount SPIFFS and download fresh audio
    if (!SPIFFS.begin(true)) {
        Serial.println("SPIFFS mount failed");
    } else {
        SPIFFS.remove("/voice.mp3");
        downloadAudio();
    }

    audio.setPinout(I2S_BCLK, I2S_LRC, I2S_DOUT);
    audio.setVolume(21);
}

// SEND SENSOR DATA
void sendSensorData() {
    ensureWiFi();

    float temperature = bme.readTemperature();
    float humidity    = bme.readHumidity();
    int   soilRaw     = analogRead(SOIL_PIN);
    float lightLux    = lightMeter.readLightLevel();

    String json = "{";
    json += "\"soilLevel\":"         + String(soilRaw)     + ",";
    json += "\"ambientLightLevel\":" + String(lightLux)    + ",";
    json += "\"humidityLevels\":"    + String(humidity)    + ",";
    json += "\"temperatureLevels\":" + String(temperature) + ",";
    json += "\"deviceId\":\""        + deviceId            + "\"";
    json += "}";

    Serial.println("Sending: " + json);

    // Retry loop — keeps retrying on -1 until success
    int code = -1;
    int attempts = 0;
    while (code < 0 && attempts < 5) {
        if (attempts > 0) {
            Serial.println("Retrying... attempt " + String(attempts + 1));
            delay(2000);
            ensureWiFi();
        }

        WiFiClientSecure client;
        client.setInsecure();
        client.setTimeout(15);

        HTTPClient http;
        http.begin(client, readingsUrl.c_str());
        http.setReuse(false);
        http.useHTTP10(true);
        http.setTimeout(10000);
        http.addHeader("Content-Type", "application/json");

        code = http.POST(json);
        if (code < 0) {
            Serial.println("Request failed: " + http.errorToString(code));
        } else {
            Serial.println("HTTP: " + String(code));
        }

        http.end();
        attempts++;
    }

    if (code < 0) {
        Serial.println("All attempts failed, will retry next cycle");
    }

    Serial.println("Free heap: " + String(esp_get_free_heap_size()));
}

// LOOP
void loop() {

    // RETRY AUDIO DOWNLOAD IF IT FAILED
    if (!audioReady && !audio.isRunning()) {
        Serial.println("Audio not ready, retrying download...");
        downloadAudio();
    }

    // SEND SENSOR DATA
    if (millis() - startTimeForRequest > 30000 && !audio.isRunning()) {
        sendSensorData();
        startTimeForRequest = millis();

        SPIFFS.remove("/voice.mp3");
        downloadAudio();
    }

    // DISTANCE TRIGGER AUDIO
    float distance = getDistance();
    if (distance > 0 && distance <= 100 && !audio.isRunning() && audioReady) {
        Serial.println("Object detected at: " + String(distance) + " cm");
        audio.connecttoFS(SPIFFS, "/voice.mp3");
    }

    audio.loop();
    delay(1);
}
