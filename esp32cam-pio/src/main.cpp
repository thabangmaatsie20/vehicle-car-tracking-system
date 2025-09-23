#include <Arduino.h>
#include <WiFi.h>

// Feature flags (can also be set via platformio.ini build_flags)
#ifndef FEAT_HTTP
#define FEAT_HTTP 1
#endif
#ifndef FEAT_EMAIL
#define FEAT_EMAIL 1
#endif
#ifndef FEAT_LCD
#define FEAT_LCD 1
#endif
#ifndef FEAT_SD
#define FEAT_SD 1
#endif

#if FEAT_HTTP
#include <HTTPClient.h>
#endif

#if FEAT_EMAIL
#include <ESP_Mail_Client.h>
#endif

#if FEAT_LCD
#include <Wire.h>
#include <LiquidCrystal_I2C.h>
#endif

#if FEAT_SD
#include <SD.h>
#include <SPI.h>
#endif

// Camera and Face libraries (come with ESP32 Arduino core)
#include "esp_camera.h"
#include "img_converters.h"
#include "fd_forward.h"
#include "fr_forward.h"
#include "dl_lib_matrix3d.h"

// User secrets/config
#include "secrets.h"

// ---- Pin definitions ----
#define BUZZER_PIN 4
#define I2C_SDA 14
#define I2C_SCL 13
#define SD_CS 15

// AI Thinker ESP32-CAM
#define PWDN_GPIO_NUM 32
#define RESET_GPIO_NUM -1
#define XCLK_GPIO_NUM 0
#define SIOD_GPIO_NUM 26
#define SIOC_GPIO_NUM 27
#define Y9_GPIO_NUM 35
#define Y8_GPIO_NUM 34
#define Y7_GPIO_NUM 39
#define Y6_GPIO_NUM 36
#define Y5_GPIO_NUM 21
#define Y4_GPIO_NUM 19
#define Y3_GPIO_NUM 18
#define Y2_GPIO_NUM 5
#define VSYNC_GPIO_NUM 25
#define HREF_GPIO_NUM 23
#define PCLK_GPIO_NUM 22

// ---- Global state ----
#if FEAT_LCD
LiquidCrystal_I2C lcd(0x27, 16, 2);
#endif

mtmn_config_t mtmn_config = {0};
fr_config_t fr_config = {0};
aligned_face_t *authorized_face = NULL;

static int attemptCount = 0;
static const int MAX_ATTEMPTS = 3;
static float dummyLat = -26.2041f;
static float dummyLng = 28.0473f;

#if FEAT_EMAIL
SMTPSession smtp;
#endif

// ---- Forward declarations ----
static bool loadAuthorizedFace();
static void sendToThingSpeak(float lat, float lng, int accessStatus, int intruderAlert);
static bool sendEmailAlert();

void setup() {
  Serial.begin(115200);
  delay(100);
  Serial.println("Starting Face Recognition");

  pinMode(BUZZER_PIN, OUTPUT);
  digitalWrite(BUZZER_PIN, LOW);

#if FEAT_LCD
  Wire.begin(I2C_SDA, I2C_SCL);
  lcd.init();
  lcd.backlight();
  lcd.setCursor(0, 0);
  lcd.print("Initializing...");
#endif

#if FEAT_SD
  if (!SD.begin(SD_CS)) {
    Serial.println("SD card init failed!");
#if FEAT_LCD
    lcd.clear();
    lcd.print("SD Error!");
#endif
    // Continue without SD if disabled via flags
  } else {
    Serial.println("SD card initialized");
  }
#endif

  // Connect WiFi
  WiFi.mode(WIFI_STA);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  Serial.print("Connecting to WiFi");
  unsigned long wifiStart = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - wifiStart < 20000) {
    delay(250);
    Serial.print('.');
  }
  Serial.println();
  if (WiFi.status() == WL_CONNECTED) {
    Serial.printf("WiFi connected: %s\n", WiFi.localIP().toString().c_str());
#if FEAT_LCD
    lcd.clear();
    lcd.print("WiFi Connected");
#endif
  } else {
    Serial.println("WiFi connect timeout");
#if FEAT_LCD
    lcd.clear();
    lcd.print("WiFi Timeout");
#endif
  }

  // Camera init
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer = LEDC_TIMER_0;
  config.pin_d0 = Y2_GPIO_NUM;
  config.pin_d1 = Y3_GPIO_NUM;
  config.pin_d2 = Y4_GPIO_NUM;
  config.pin_d3 = Y5_GPIO_NUM;
  config.pin_d4 = Y6_GPIO_NUM;
  config.pin_d5 = Y7_GPIO_NUM;
  config.pin_d6 = Y8_GPIO_NUM;
  config.pin_d7 = Y9_GPIO_NUM;
  config.pin_xclk = XCLK_GPIO_NUM;
  config.pin_pclk = PCLK_GPIO_NUM;
  config.pin_vsync = VSYNC_GPIO_NUM;
  config.pin_href = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn = PWDN_GPIO_NUM;
  config.pin_reset = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_RGB565;
  config.frame_size = FRAMESIZE_QVGA;
  config.jpeg_quality = 12;
  config.fb_count = 2;

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("Camera init failed: 0x%x\n", err);
#if FEAT_LCD
    lcd.clear();
    lcd.print("Camera Error!");
#endif
    delay(5000);
  }

  // Face detection/recognition
  mtmn_config = mtmn_init_config();
  fr_config = fr_init_config();

  // Load authorized face (from SD/jpeg)
  if (!loadAuthorizedFace()) {
    Serial.println("No authorized face loaded");
#if FEAT_LCD
    lcd.clear();
    lcd.print("No Face Loaded!");
#endif
  }

#if FEAT_LCD
  lcd.clear();
  lcd.setCursor(0, 0);
  lcd.print("Present your face");
  lcd.setCursor(0, 1);
  lcd.print("to authorize");
#endif
}

void loop() {
  camera_fb_t *fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("Camera capture failed");
    delay(500);
    return;
  }

  dl_matrix3du_t *image_matrix = dl_matrix3du_alloc(1, fb->width, fb->height, 3);
  if (!image_matrix) {
    Serial.println("dl_matrix3du_alloc failed");
    esp_camera_fb_return(fb);
    delay(200);
    return;
  }

  fmt2rgb888(fb->buf, fb->len, fb->format, image_matrix->item);
  box_array_t *net_boxes = face_detect(image_matrix, &mtmn_config);

  bool face_detected = (net_boxes && net_boxes->len > 0);
  bool face_recognized = false;
  int accessStatus = 0;
  int intruderAlert = 0;

  if (face_detected && authorized_face) {
    aligned_face_t *aligned = aligned_face_alloc();
    if (aligned) {
      for (int i = 0; i < net_boxes->len; i++) {
        if (aligned_face_align(image_matrix, net_boxes->box[i], aligned)) {
          float score = fr_recognize_face(aligned, authorized_face);
          if (score > 0.6f) {
            face_recognized = true;
            break;
          }
        }
      }
      aligned_face_free(aligned);
    }
  }

  if (face_recognized) {
#if FEAT_LCD
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Access Granted");
#endif
    accessStatus = 1;
    attemptCount = 0;
    Serial.println("Face recognized!");
  } else {
#if FEAT_LCD
    lcd.clear();
    lcd.setCursor(0, 0);
    lcd.print("Access Denied");
    lcd.setCursor(0, 1);
    lcd.print("Not Allowed!");
#endif
    digitalWrite(BUZZER_PIN, HIGH);
    delay(500);
    digitalWrite(BUZZER_PIN, LOW);
    attemptCount++;
    Serial.printf("No match - attempt: %d\n", attemptCount);
    if (attemptCount >= MAX_ATTEMPTS) {
      intruderAlert = 1;
      (void)sendEmailAlert();
      attemptCount = 0;
    }
  }

  sendToThingSpeak(dummyLat, dummyLng, accessStatus, intruderAlert);

  if (net_boxes) {
    dl_lib_free(net_boxes->score);
    dl_lib_free(net_boxes->box);
    dl_lib_free(net_boxes->landmark);
    dl_lib_free(net_boxes);
  }
  dl_matrix3du_free(image_matrix);
  esp_camera_fb_return(fb);

  delay(2000);
}

// ---- Helpers ----
static bool loadAuthorizedFace() {
#if FEAT_SD
  File file = SD.open("/faces/user1.jpg", FILE_READ);
  if (!file) {
    Serial.println("Failed to open /faces/user1.jpg");
    return false;
  }

  size_t size = file.size();
  uint8_t *buffer = (uint8_t *)malloc(size);
  if (!buffer) {
    Serial.println("Memory allocation failed");
    file.close();
    return false;
  }
  file.read(buffer, size);
  file.close();

  dl_matrix3du_t *image = dl_matrix3du_alloc(1, 320, 240, 3);
  if (!image) {
    Serial.println("Image allocation failed");
    free(buffer);
    return false;
  }
  if (!fmt2rgb888(buffer, size, PIXFORMAT_JPEG, image->item)) {
    Serial.println("JPEG decode failed");
    dl_matrix3du_free(image);
    free(buffer);
    return false;
  }
  free(buffer);

  box_array_t *boxes = face_detect(image, &mtmn_config);
  if (!boxes || boxes->len == 0) {
    Serial.println("No face detected in user1.jpg");
    dl_matrix3du_free(image);
    if (boxes) {
      dl_lib_free(boxes->score);
      dl_lib_free(boxes->box);
      dl_lib_free(boxes->landmark);
      dl_lib_free(boxes);
    }
    return false;
  }

  authorized_face = aligned_face_alloc();
  if (!authorized_face || !aligned_face_align(image, boxes->box[0], authorized_face)) {
    Serial.println("Face alignment failed");
    dl_matrix3du_free(image);
    dl_lib_free(boxes->score);
    dl_lib_free(boxes->box);
    dl_lib_free(boxes->landmark);
    dl_lib_free(boxes);
    if (authorized_face) {
      aligned_face_free(authorized_face);
      authorized_face = NULL;
    }
    return false;
  }

  dl_matrix3du_free(image);
  dl_lib_free(boxes->score);
  dl_lib_free(boxes->box);
  dl_lib_free(boxes->landmark);
  dl_lib_free(boxes);
  Serial.println("Authorized face loaded");
  return true;
#else
  // SD disabled; cannot load face
  return false;
#endif
}

static void sendToThingSpeak(float lat, float lng, int accessStatus, int intruderAlert) {
#if FEAT_HTTP
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("WiFi disconnected, skip ThingSpeak");
    return;
  }
  HTTPClient http;
  String url = String("http://api.thingspeak.com/update?api_key=") + THINGSPEAK_API_KEY +
               "&field1=" + String(lat, 6) +
               "&field2=" + String(lng, 6) +
               "&field3=" + String(intruderAlert) +
               "&field4=" + String(accessStatus);
  http.begin(url);
  int httpCode = http.GET();
  if (httpCode > 0) {
    Serial.printf("ThingSpeak update code: %d\n", httpCode);
  } else {
    Serial.printf("ThingSpeak failed: %s\n", http.errorToString(httpCode).c_str());
  }
  http.end();
#else
  (void)lat; (void)lng; (void)accessStatus; (void)intruderAlert;
#endif
}

static bool sendEmailAlert() {
#if FEAT_EMAIL
  smtp.debug(0);
  ESP_Mail_Session session;
  session.server.host_name = SMTP_HOST;
  session.server.port = SMTP_PORT;
  session.login.email = SENDER_EMAIL;
  session.login.password = SENDER_PASSWORD;
  session.login.user_domain = "gmail.com";

  SMTP_Message message;
  message.sender.name = "Vehicle Security";
  message.sender.email = SENDER_EMAIL;
  message.subject = "Intruder Alert!";
  message.addRecipient("User", RECEIVER_EMAIL);
  String textMsg = String("An intruder tried to use the vehicle! Check: ") + DASHBOARD_LINK;
  message.text.content = textMsg.c_str();

  if (!smtp.connect(&session)) {
    Serial.println("SMTP connect failed");
    return false;
  }
  if (!MailClient.sendMail(&smtp, &message)) {
    Serial.println("Email send failed");
    return false;
  }
  return true;
#else
  return false;
#endif
}
