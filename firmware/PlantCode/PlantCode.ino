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
#define SOIL_PIN 19
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

// ---------------- SENSORS ----------------
Adafruit_BME280 bme;
BH1750 lightMeter;

// ---------------- AUDIO ----------------
Audio audio;
bool audioPlaying = false;

// ---------------- TIMING ----------------
unsigned long startTimeForRequest = 0;

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
    int   soilRaw;
    float lightLux;
};

volatile bool postInProgress = false;
unsigned long postStartTime = 0;
#define POST_TIMEOUT_MS 30000

void postTask(void* param) {
    SensorData* data = (SensorData*)param;

    String json = "{";
    json += "\"soilLevel\":"          + String(data->soilRaw)      + ",";
    json += "\"ambientLightLevel\":"  + String(data->lightLux)     + ",";
    json += "\"humidityLevels\":"     + String(data->humidity)     + ",";
    json += "\"temperatureLevels\":"  + String(data->temperature)  + ",";
    json += "\"deviceId\":\""         + deviceId                   + "\"";
    json += "}";
    Serial.println(json);

    WiFiClientSecure client;
    client.setInsecure();
    HTTPClient http;
    http.setConnectTimeout(10000);
    http.setTimeout(15000);
    http.begin(client, readingsUrl.c_str());
    http.addHeader("Content-Type", "application/json");
    int code = http.POST(json);
    Serial.println("HTTP: " + String(code));
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
    
    if (millis() - startTimeForRequest > 5000 && !postInProgress && !audioPlaying) {

        ensureWiFi();


        SensorData* data = new SensorData();
        data->temperature = bme.readTemperature();
        data->humidity    = bme.readHumidity();
        data->soilRaw     = analogRead(SOIL_PIN);
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
    if (distance > 0 && distance <= 100 && !audioPlaying) {
        Serial.println(distance);
        ensureWiFi();
        Serial.println("Object detected!");
        audio.connecttohost(voiceUrl.c_str());
        audioPlaying = true;
    }

    audio.loop();
    delay(1);
}