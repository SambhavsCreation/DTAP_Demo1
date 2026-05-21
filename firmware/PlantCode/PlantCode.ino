#include "Arduino.h"
#include "Audio.h"
#include "WiFi.h"
#include <HTTPClient.h>
#include <Wire.h>
#include <Adafruit_BME280.h>
#include <BH1750.h>
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"

// ---------------- PINS ----------------
#define I2S_LRC  17
#define I2S_BCLK 16
#define I2S_DOUT 4
#define TRIG_PIN 18
#define ECHO_PIN 5
// Use an ADC-capable pin for soil moisture reads on ESP32.
#define SOIL_PIN 34
#define SDA_PIN 21
#define SCL_PIN 22

// ---------------- WIFI ----------------
String ssid = "aalto open";
String password = "";
String serverUrl = "https://dtap-demo1.onrender.com";
String readingsUrl = serverUrl + "/api/readings/";
String voiceUrl = serverUrl + "/api/plant/voice/";
String deviceId = "POT-12345";

#define WIFI_TIMEOUT_MS   10000   // 10 s to establish connection
#define WIFI_RECOVER_MS   30000   // wait 30 s before retrying after failure
#define POST_INTERVAL_MS  5000    // 5 s between uploads
#define VOICE_COOLDOWN_MS 15000   // 15 s between voice trigger attempts
#define AUDIO_SESSION_TIMEOUT_MS 45000

// ---------------- SENSORS ----------------
Adafruit_BME280 bme;
BH1750 lightMeter;

// ---------------- AUDIO ----------------
Audio audio;
bool audioPlaying = false;

// ---------------- TIMING ----------------
unsigned long startTimeForRequest = 0;
unsigned long lastVoiceTriggerAt = 0;
unsigned long audioStartedAt = 0;

// ---------------- WIFI RECONNECT ----------------
void ensureWiFi() {
    if (WiFi.status() == WL_CONNECTED) return;

    Serial.println("WiFi lost — reconnecting...");
    WiFi.disconnect(true);
    WiFi.begin(ssid.c_str(), password.c_str());

    unsigned long start = millis();
    while (WiFi.status() != WL_CONNECTED) {
        if (millis() - start > WIFI_TIMEOUT_MS) {
            Serial.println("WiFi reconnect timed out. Will retry later.");
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

struct SensorData {
    float temperature;
    float humidity;
    int   soilPercent;
    float lightLux;
};

volatile bool postInProgress = false;
unsigned long postStartTime = 0;
#define POST_TIMEOUT_MS 30000

void postTask(void* param) {
    SensorData* data = (SensorData*)param;

    String json = "{";
    json += "\"soilLevel\":"          + String(data->soilPercent)  + ",";
    json += "\"ambientLightLevel\":"  + String(data->lightLux)     + ",";
    json += "\"humidityLevels\":"     + String(data->humidity)     + ",";
    json += "\"temperatureLevels\":"  + String(data->temperature)  + ",";
    json += "\"deviceId\":\""         + deviceId                   + "\"";
    json += "}";
    Serial.println(json);

    WiFiClientSecure client;
    client.setInsecure();
    HTTPClient http;
    http.begin(client, readingsUrl.c_str());
    http.setConnectTimeout(8000);
    http.setTimeout(15000);
    http.addHeader("Content-Type", "application/json");
    int code = http.POST(json);
    if (code > 0) {
        Serial.println("POST /readings status: " + String(code));
    } else {
        Serial.println("POST /readings failed: " + http.errorToString(code));
    }
    http.end();

    delete data;        
    postInProgress = false;
    vTaskDelete(NULL); 
}

// ---------------- AUDIO CALLBACKS ----------------
void audio_info(const char* info){
    Serial.println(info);
}
void audio_eof_stream(const char *info){
    Serial.println("Audio finished");
    audioPlaying = false;
    audioStartedAt = 0;
}

// ---------------- ULTRASONIC ----------------
float getDistance(){
    digitalWrite(TRIG_PIN, LOW);
    delayMicroseconds(2);
    digitalWrite(TRIG_PIN, HIGH);
    delayMicroseconds(10);
    digitalWrite(TRIG_PIN, LOW);
    long duration = pulseIn(ECHO_PIN, HIGH, 5000);
    return duration * 0.034 / 2;
}

// ---------------- SETUP ----------------
void setup(){
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
    while (WiFi.status() != WL_CONNECTED){
        delay(500);
        Serial.print(".");
    }
    Serial.println("\nWiFi connected. IP: " + WiFi.localIP().toString());

    audio.setPinout(I2S_BCLK, I2S_LRC, I2S_DOUT);
    audio.setVolume(21);
}

// ---------------- LOOP ----------------
void loop(){
    // ----------- SEND SENSOR DATA -----------
    if (audioPlaying && millis() - audioStartedAt > AUDIO_SESSION_TIMEOUT_MS) {
        Serial.println("Audio session timeout - resetting audio state");
        audio.stopSong();
        audioPlaying = false;
        audioStartedAt = 0;
    }

    if (millis() - startTimeForRequest > POST_INTERVAL_MS && !postInProgress && !audioPlaying) {

        ensureWiFi();


        SensorData* data = new SensorData();
        data->temperature = bme.readTemperature();
        data->humidity    = bme.readHumidity();
        int rawSoil       = constrain(analogRead(SOIL_PIN), 0, 4095);
        data->soilPercent = map(rawSoil, 0, 4095, 0, 100);
        data->lightLux    = lightMeter.readLightLevel();

        postInProgress = true;
        postStartTime = millis();
        xTaskCreatePinnedToCore(
            postTask,    
            "postTask",  
            8192,        
            data,        
            1,           
            NULL,        
            0            
        );

        startTimeForRequest = millis();
    }

    if (postInProgress && millis() - postStartTime > POST_TIMEOUT_MS) {
        Serial.println("POST timed out — resetting postInProgress");
        postInProgress = false;
    }
    

    // ----------- DISTANCE TRIGGER AUDIO -----------
    float distance = getDistance();
    bool voiceCooldownElapsed = (millis() - lastVoiceTriggerAt) >= VOICE_COOLDOWN_MS;
    if (distance > 0 && distance <= 100 && !audioPlaying && voiceCooldownElapsed) {
        Serial.println(distance);
        ensureWiFi();
        Serial.println("Object detected!");
        String scopedVoiceUrl = voiceUrl + "?deviceId=" + deviceId;
        bool started = audio.connecttohost(scopedVoiceUrl.c_str());
        if (started) {
            audioPlaying = true;
            audioStartedAt = millis();
            lastVoiceTriggerAt = millis();
        } else {
            Serial.println("Audio start failed");
            audioPlaying = false;
            audioStartedAt = 0;
        }
    }

    audio.loop();
    delay(1);
}
