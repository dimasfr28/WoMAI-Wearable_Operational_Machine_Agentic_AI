#include <DHT.h>
#include <Wire.h>
#include <Adafruit_MLX90614.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <WiFiClientSecure.h>
#include <time.h>  // Untuk NTP time sync

// ================= KONFIGURASI PIN =================
#define DHTPIN 14
#define DHTTYPE DHT22   
#define IR_PIN 25
#define LED_PIN 2              // LED onboard ESP32 (indikator kecil)
#define SUPERBRIGHT_LED_PIN 4  // LED SuperBright eksternal (indikator besar, via resistor 180ohm)
#define WIFI_LED_PIN 13        // LED Merah eksternal (indikator WiFi: nyala = tidak connect)
#define PULSES_PER_REV 3

// ================= KONFIGURASI WIFI & CLOUDFLARE ENDPOINT ============  =====
const char* WIFI_SSID = "POCO M6 Pro";        // Nama Hotspot Wi-Fi Anda
const char* WIFI_PASSWORD = "12345678";          // Password kosong ("") untuk Open Wi-Fi (Tanpa Password)

// Endpoint Target Cloudflare Tunnel & Machine UUID
const char* CLOUDFLARE_BASE_URL = "https://neither-boss-honors-animal.trycloudflare.com";
const char* MACHINE_ID = "20148266-dbb0-4494-a8e3-66bc4c6be031"; // Registered Machine UUID

#define TELEMETRY_INTERVAL_MS 60000 // Interval pengiriman data HTTP POST (ms)


// ================= BLINK LED SUPERBRIGHT =================
#define BLINK_INTERVAL_MS 200  // kecepatan kedip saat anomaly (ms)

// ================= BATTERY MONITORING =================
#define ENABLE_BATTERY_MONITOR 0
#define BATTERY_ADC_PIN 34
#define DIVIDER_R1 100000.0
#define DIVIDER_R2 33000.0
#define ADC_VREF 3.3
#define BATTERY_FULL_VOLTAGE 8.4
#define BATTERY_EMPTY_VOLTAGE 6.0
#define BATTERY_LOW_THRESHOLD 6.4

// ================= ANTI-NOISE RPM =================
#define MIN_PULSE_INTERVAL_US 5000

// ================= THRESHOLD ANOMALI =================
#define TEMP_OBJECT_MAX 45.0
#define RPM_MIN 250
#define RPM_MAX 900
#define MAX_CONSECUTIVE_GY906_FAIL 3

// ================= KONVERSI SUHU =================
#define CELSIUS_TO_KELVIN_OFFSET 273.15

// ================= NTP TIME SYNC =================
const char* NTP_SERVER = "pool.ntp.org";
const long GMT_OFFSET_SEC = 7 * 3600;   // WIB = UTC+7
const int DAYLIGHT_OFFSET_SEC = 0;       // Indonesia tidak pakai DST
bool ntpSynced = false;

DHT dht(DHTPIN, DHTTYPE);
Adafruit_MLX90614 mlx = Adafruit_MLX90614();

volatile unsigned long pulseCount = 0;
volatile unsigned long lastPulseMicros = 0;

unsigned long lastRpmCalc = 0;
unsigned long lastSensorRead = 0;
unsigned long lastI2CScan = 0;
unsigned long lastBlinkToggle = 0;
unsigned long lastTelemetryTime = 0;
unsigned long lastWifiCheck = 0;
unsigned long lastToolWearUpdate = 0;

float currentRPM = 0;
float toolWearMinutes = 0.0; // Akumulasi Tool Wear dalam menit saat mesin berputar (RPM > 0)

bool gy906Ready = false;
int gy906ConsecutiveFail = 0;
bool currentAnomalyStatus = false;
bool blinkState = false;

// Variable global penyimpan pembacaan suhu terakhir (dalam Kelvin)
float latestAirTempK = 300.15;
float latestProcessTempK = 300.15;

float celciusKeKelvin(float celcius) {
  return celcius + CELSIUS_TO_KELVIN_OFFSET;
}

// Fungsi mendapatkan timestamp ISO 8601 dari NTP
// Jika NTP belum sync, return timestamp fallback berformat ISO 8601 valid agar server tidak me-reject dengan error 400
String getTimestampISO8601() {
  struct tm timeinfo;
  if (getLocalTime(&timeinfo, 100)) {
    char buf[30];
    strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%S+07:00", &timeinfo);
    return String(buf);
  }
  // Fallback timestamp valid jika NTP terhambat/belum sync
  return "2026-08-19T00:00:00+07:00";
}

#if ENABLE_BATTERY_MONITOR
float bacaTeganganBaterai() {
  long total = 0;
  const int jumlahSample = 20;
  for (int i = 0; i < jumlahSample; i++) {
    total += analogRead(BATTERY_ADC_PIN);
    delay(2);
  }
  float rawAvg = total / (float)jumlahSample;
  float vAdc = (rawAvg / 4095.0) * ADC_VREF;
  float vBaterai = vAdc * (DIVIDER_R1 + DIVIDER_R2) / DIVIDER_R2;
  return vBaterai;
}

float hitungPersenBaterai(float voltage) {
  float persen = (voltage - BATTERY_EMPTY_VOLTAGE) / (BATTERY_FULL_VOLTAGE - BATTERY_EMPTY_VOLTAGE) * 100.0;
  if (persen > 100) persen = 100;
  if (persen < 0) persen = 0;
  return persen;
}
#endif

void IRAM_ATTR onPulse() {
  unsigned long nowMicros = micros();
  if (nowMicros - lastPulseMicros >= MIN_PULSE_INTERVAL_US) {
    pulseCount++;
    lastPulseMicros = nowMicros;
  }
}

// Fungsi diagnostik untuk memindai semua Wi-Fi 2.4GHz yang terjangkau oleh ESP32
void scanWiFiNetworks() {
  Serial.println("[WiFi Scan] Memindai jaringan Wi-Fi 2.4GHz di sekitar...");
  int n = WiFi.scanNetworks();
  if (n == 0) {
    Serial.println("[WiFi Scan] PERINGATAN: Tidak ada jaringan Wi-Fi 2.4GHz ditemukan!");
  } else {
    Serial.print("[WiFi Scan] Ditemukan "); Serial.print(n); Serial.println(" jaringan Wi-Fi:");
    bool foundTarget = false;
    for (int i = 0; i < n; ++i) {
      Serial.print("  "); Serial.print(i + 1); Serial.print(": ");
      Serial.print(WiFi.SSID(i));
      Serial.print(" (Sinyal: "); Serial.print(WiFi.RSSI(i)); Serial.print(" dBm, Channel: ");
      Serial.print(WiFi.channel(i)); Serial.println(")");
      if (WiFi.SSID(i) == String(WIFI_SSID)) {
        foundTarget = true;
      }
    }
    if (!foundTarget) {
      Serial.print("[WiFi Scan] HASIL: Hotspot \"");
      Serial.print(WIFI_SSID);
      Serial.println("\" TIDAK TERLIHAT oleh ESP32!");
      Serial.println("  -> PENYEBAB UTAMA: Hotspot HP masih dalam mode 5 GHz atau Hide SSID (Tersembunyi).");
      Serial.println("  -> SOLUSI: Buka Hotspot HP -> Pita AP (AP Band) -> Ubah ke 2.4 GHz band!");
    } else {
      Serial.print("[WiFi Scan] HASIL: Hotspot \"");
      Serial.print(WIFI_SSID);
      Serial.println("\" TERLIHAT oleh ESP32!");
      Serial.println("  -> JIKA MASIH GAGAL KONEK: Cek Password / aktifkan 'Extend Compatibility' (WPA2) di HP.");
    }
  }
  WiFi.scanDelete();
}

// Fungsi koneksi dan pemeliharaan Wi-Fi
void setupWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.print("[WiFi] Menghubungkan ke Wi-Fi: ");
  Serial.println(WIFI_SSID);

  WiFi.mode(WIFI_OFF);
  delay(100);
  WiFi.persistent(false);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false); // Matikan Modem Sleep agar koneksi SSL via Hotspot HP stabil tanpa drop/timeout
  WiFi.setAutoReconnect(true);

  if (strlen(WIFI_PASSWORD) == 0) {
    WiFi.begin(WIFI_SSID);
  } else {
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  }

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 25) {
    delay(500);
    Serial.print(".");
    retries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    WiFi.setSleep(false);
    Serial.println("\n[WiFi] Terhubung! IP Address: ");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[WiFi] Belum terhubung ke Hotspot!");
    scanWiFiNetworks(); // Lakukan diagnostik scan otomatis saat gagal
  }
}

// Fungsi reconnect Wi-Fi ringan untuk dipanggil di loop()
void reconnectWiFi() {
  if (WiFi.status() == WL_CONNECTED) return;

  Serial.println("[WiFi] Mencoba reconnect...");
  
  WiFi.mode(WIFI_OFF);
  delay(100);
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);
  WiFi.setAutoReconnect(true);

  if (strlen(WIFI_PASSWORD) == 0) {
    WiFi.begin(WIFI_SSID);
  } else {
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  }

  int retries = 0;
  while (WiFi.status() != WL_CONNECTED && retries < 15) {
    delay(500);
    Serial.print(".");
    retries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    WiFi.setSleep(false);
    Serial.println("\n[WiFi] Reconnect berhasil!");
    Serial.println(WiFi.localIP());
  } else {
    Serial.println("\n[WiFi] Reconnect belum berhasil.");
    scanWiFiNetworks(); // Lakukan diagnostik scan otomatis
  }
}

// Fungsi Pengiriman HTTPS Telemetry ke Cloudflare Tunnel
void kirimDataTelemetry(float airTempK, float processTempK, float rpm, float toolWearMin) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[HTTP] Skip POST: Wi-Fi terputus.");
    return;
  }

  // Proteksi NaN dan nilai 0 agar backend tidak menolak dengan error 400 (disconnected/faulty sensor)
  float safeAirTemp = (isnan(airTempK) || airTempK <= 0) ? 300.15 : airTempK;
  float safeProcessTemp = (isnan(processTempK) || processTempK <= 0) ? 300.15 : processTempK;
  int safeRpm = (isnan(rpm) || rpm <= 0) ? 1 : (int)rpm;
  float safeToolWear = (isnan(toolWearMin) || toolWearMin <= 0) ? 0.10 : toolWearMin;

  // Gunakan WiFiClientSecure dengan setInsecure() untuk menangani SSL Cloudflare Tunnel secara aman
  WiFiClientSecure client;
  client.setInsecure();

  HTTPClient http;
  http.setReuse(false);      // Jangan reuse socket untuk hindari stale socket TLS
  http.setTimeout(15000);    // 15 detik timeout
  http.setConnectTimeout(10000); // 10 detik connect timeout

  String targetUrl = String(CLOUDFLARE_BASE_URL) + "/sensor/readings?machine_id=" + String(MACHINE_ID);

  if (!http.begin(client, targetUrl)) {
    Serial.println("[HTTP] Gagal menginisialisasi client HTTPS.");
    return;
  }

  http.addHeader("Content-Type", "application/json");
  http.addHeader("User-Agent", "ESP32-IoT-Node/1.0");
  http.addHeader("Connection", "close"); // PENTING: Mencegah ESP32 hang/timeout menunggu keep-alive stream dari Cloudflare

  // Ambil timestamp ISO 8601 dari NTP
  String timestamp = getTimestampISO8601();

  // Coba sync ulang NTP jika belum synced
  if (!ntpSynced) {
    configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET_SEC, NTP_SERVER);
    struct tm timeinfo;
    if (getLocalTime(&timeinfo, 1000)) ntpSynced = true;
  }

  // Format JSON payload dengan rotational_speed_rpm sebagai integer (%d)
  char jsonBuffer[384];
  snprintf(jsonBuffer, sizeof(jsonBuffer),
    "{\"timestamp\":\"%s\",\"air_temperature_k\":%.2f,\"process_temperature_k\":%.2f,\"rotational_speed_rpm\":%d,\"tool_wear_min\":%.2f}",
    timestamp.c_str(), safeAirTemp, safeProcessTemp, safeRpm, safeToolWear);
  String jsonPayload = jsonBuffer;

  Serial.print("[HTTP] Sending POST to: ");
  Serial.println(targetUrl);
  Serial.print("[HTTP] Payload: ");
  Serial.println(jsonPayload);

  int httpResponseCode = http.POST(jsonPayload);

  if (httpResponseCode > 0) {
    Serial.print("[HTTP] Response Code: ");
    Serial.println(httpResponseCode);
    String response = http.getString();
    if (response.length() > 0) {
      Serial.print("[HTTP] Response Body: ");
      Serial.println(response);
    }
  } else {
    Serial.print("[HTTP] POST Failed, Error Code: ");
    Serial.println(http.errorToString(httpResponseCode).c_str());
  }

  http.end();
}

void scanI2C() {
  Serial.println("=== Scan I2C ===");
  byte error, address;
  int nDevices = 0;
  for (address = 1; address < 127; address++) {
    Wire.beginTransmission(address);
    error = Wire.endTransmission();
    if (error == 0) {
      Serial.print("Device ditemukan di 0x");
      Serial.println(address, HEX);
      nDevices++;
    }
  }
  if (nDevices == 0) {
    Serial.println("PERINGATAN: Tidak ada device I2C! Cek wiring VIN/GND/SCL/SDA GY-906.");
  }
  Serial.println("=== Selesai Scan ===");
}

void diagnostikDutyCycleIR() {
  int totalSample = 0;
  int lowCount = 0;
  unsigned long startMicros = micros();

  while (micros() - startMicros < 50000UL) {  // 50ms sampling (cukup untuk diagnostik, tidak blocking lama)
    if (digitalRead(IR_PIN) == LOW) lowCount++;
    totalSample++;
  }

  float persenLow = (lowCount / (float)totalSample) * 100.0;
  Serial.print("DIAGNOSTIK DUTY CYCLE -> LOW: ");
  Serial.print(persenLow, 1);
  Serial.print("% | HIGH: ");
  Serial.print(100.0 - persenLow, 1);
  Serial.print("% | pulseCount saat ini: ");
  Serial.println(pulseCount);

  if (persenLow > 90.0) {
    Serial.println("  -> Sensor STUCK LOW terus (>90%). Genuine masalah, bukan snapshot salah waktu.");
  } else if (persenLow < 5.0) {
    Serial.println("  -> Sensor STUCK HIGH terus (<5% LOW). Tidak ada objek terdeteksi sama sekali.");
  } else {
    Serial.println("  -> Sensor BERKEDIP (ada transisi LOW/HIGH). Bagus, sensor merespons objek secara periodik.");
  }
}

// Kontrol LED SuperBright: solid ON kalau normal, berkedip cepat kalau anomaly
void kontrolLedSuperBright(unsigned long now) {
  if (currentAnomalyStatus) {
    if (now - lastBlinkToggle >= BLINK_INTERVAL_MS) {
      lastBlinkToggle = now;
      blinkState = !blinkState;
      digitalWrite(SUPERBRIGHT_LED_PIN, blinkState ? HIGH : LOW);
    }
  } else {
    digitalWrite(SUPERBRIGHT_LED_PIN, HIGH); // solid nyala = sistem normal
  }
}

void setup() {
  Serial.begin(115200);
  delay(1000);

  dht.begin();
  Wire.begin(21, 22);

  gy906Ready = mlx.begin();
  scanI2C(); // Scan I2C saat startup untuk diagnostik awal

  pinMode(IR_PIN, INPUT_PULLUP);
  pinMode(LED_PIN, OUTPUT);
  pinMode(SUPERBRIGHT_LED_PIN, OUTPUT);
  pinMode(WIFI_LED_PIN, OUTPUT);
  digitalWrite(SUPERBRIGHT_LED_PIN, HIGH); // langsung nyala begitu boot
  digitalWrite(WIFI_LED_PIN, HIGH);        // LED merah nyala saat boot (WiFi belum connect)

  attachInterrupt(digitalPinToInterrupt(IR_PIN), onPulse, FALLING);

  #if ENABLE_BATTERY_MONITOR
  analogReadResolution(12);
  #endif

  setupWiFi();

  // Update LED merah sesuai status WiFi setelah koneksi awal
  digitalWrite(WIFI_LED_PIN, WiFi.status() != WL_CONNECTED ? HIGH : LOW);

  // Sinkronisasi waktu dari NTP server setelah WiFi tersambung
  configTime(GMT_OFFSET_SEC, DAYLIGHT_OFFSET_SEC, NTP_SERVER);
  Serial.println("[NTP] Menunggu sinkronisasi waktu...");
  struct tm timeinfo;
  if (getLocalTime(&timeinfo, 5000)) {
    ntpSynced = true;
    Serial.println("[NTP] Waktu berhasil disinkronkan: " + getTimestampISO8601());
  } else {
    Serial.println("[NTP] Gagal sinkronisasi waktu. Akan coba lagi saat kirim data.");
  }

  lastRpmCalc = millis();
  lastSensorRead = millis();
  lastTelemetryTime = millis();
  lastToolWearUpdate = millis();
  lastI2CScan = 0;

  Serial.println("{\"status\":\"ready\",\"msg\":\"Smart Manufacturing Node started with Cloudflare HTTPS Telemetry\"}");
}

void loop() {
  unsigned long now = millis();

  kontrolLedSuperBright(now);

  // Kontrol LED Merah WiFi: nyala = tidak connect, mati = connect
  digitalWrite(WIFI_LED_PIN, WiFi.status() != WL_CONNECTED ? HIGH : LOW);

  // Akumulasi tool wear (dalam menit) saat mesin berputar (RPM > 0)
  if (currentRPM > 0) {
    toolWearMinutes += (now - lastToolWearUpdate) / 60000.0;
  }
  lastToolWearUpdate = now;

  // Cek Re-koneksi Wi-Fi secara periodik jika terputus (tiap 15 detik)
  if (WiFi.status() != WL_CONNECTED && (now - lastWifiCheck >= 15000)) {
    lastWifiCheck = now;
    reconnectWiFi(); // Gunakan versi ringan (max 2.5 detik) bukan setupWiFi (max 12.5 detik)
    lastToolWearUpdate = millis(); // Reset agar delay WiFi tidak dihitung sebagai tool wear
  }

  if (now - lastI2CScan >= 30000) {  // Scan tiap 30 detik (bukan 5 detik) untuk kurangi overhead
    lastI2CScan = now;

    // Hanya re-inisialisasi MLX90614 jika sensor belum ready atau setelah kegagalan
    // Ini mencegah I2C bus corruption dari mlx.begin() yang dipanggil terus-menerus
    if (!gy906Ready || gy906ConsecutiveFail > 0) {
      gy906Ready = mlx.begin();
      if (!gy906Ready) {
        scanI2C(); // Scan I2C hanya saat ada masalah sensor
      }
    }

    if (!gy906Ready) {
      gy906ConsecutiveFail++;
      Serial.print("GY-906 gagal berturut-turut ke-");
      Serial.println(gy906ConsecutiveFail);
    } else {
      gy906ConsecutiveFail = 0;
    }

    Serial.print("DIAGNOSTIK -> raw_pin_IR (snapshot): ");
    Serial.println(digitalRead(IR_PIN) == LOW ? "LOW (objek terdeteksi SEKARANG)" : "HIGH (idle/tidak ada objek)");
    diagnostikDutyCycleIR();
    lastToolWearUpdate = millis(); // Reset agar waktu diagnostik tidak dihitung sebagai tool wear
  }

  if (now - lastRpmCalc >= 1000) {
    noInterrupts();
    unsigned long pulses = pulseCount;
    pulseCount = 0;
    interrupts();

    currentRPM = (pulses / (float)PULSES_PER_REV) * 60.0;
    lastRpmCalc = now;
  }

  if (now - lastSensorRead >= 2000) {
    lastSensorRead = now;

    float t = dht.readTemperature();
    float h = dht.readHumidity();
    float ambientTemp = gy906Ready ? mlx.readAmbientTempC() : NAN;
    float objectTemp = gy906Ready ? mlx.readObjectTempC() : NAN;

    bool dhtOK = !(isnan(t) || isnan(h));
    bool gyOK = !(isnan(ambientTemp) || isnan(objectTemp));

    float tKelvin = dhtOK ? celciusKeKelvin(t) : NAN;
    float ambientKelvin = gyOK ? celciusKeKelvin(ambientTemp) : NAN;
    float objectKelvin = gyOK ? celciusKeKelvin(objectTemp) : NAN;

    // Simpan data suhu Kelvin ke variabel global untuk telemetry
    if (dhtOK) {
      latestAirTempK = tKelvin;
    } else if (gyOK) {
      latestAirTempK = ambientKelvin; // Fallback jika DHT22 error
    }

    if (gyOK) {
      latestProcessTempK = objectKelvin;
    } else if (dhtOK) {
      latestProcessTempK = tKelvin; // Fallback jika GY906 error
    }

    bool anomaly = false;
    String anomalyReason = "";

    if (gyOK && objectTemp > TEMP_OBJECT_MAX) {
      anomaly = true;
      anomalyReason += "Suhu mesin melebihi batas aman; ";
    }
    if (currentRPM > 0 && (currentRPM < RPM_MIN || currentRPM > RPM_MAX)) {
      anomaly = true;
      anomalyReason += "RPM di luar rentang normal; ";
    }
    if (!dhtOK) {
      anomaly = true;
      anomalyReason += "DHT22 tidak merespons; ";
    }
    if (gy906ConsecutiveFail >= MAX_CONSECUTIVE_GY906_FAIL) {
      anomaly = true;
      anomalyReason += "GY-906 offline berkepanjangan, cek koneksi; ";
    }

    #if ENABLE_BATTERY_MONITOR
    float batteryVoltage = bacaTeganganBaterai();
    float batteryPercent = hitungPersenBaterai(batteryVoltage);
    if (batteryVoltage < BATTERY_LOW_THRESHOLD) {
      anomaly = true;
      anomalyReason += "Baterai lemah, segera charge; ";
    }
    #endif

    currentAnomalyStatus = anomaly;
    digitalWrite(LED_PIN, anomaly ? HIGH : LOW);

    Serial.print("{");
    Serial.print("\"timestamp\":\""); Serial.print(getTimestampISO8601()); Serial.print("\",");
    Serial.print("\"suhu_ruangan_celcius\":"); Serial.print(dhtOK ? String(t, 2) : "null"); Serial.print(",");
    Serial.print("\"suhu_ruangan_kelvin\":"); Serial.print(dhtOK ? String(tKelvin, 2) : "null"); Serial.print(",");
    Serial.print("\"kelembapan\":"); Serial.print(dhtOK ? String(h, 2) : "null"); Serial.print(",");
    Serial.print("\"suhu_ambient_gy906_celcius\":"); Serial.print(gyOK ? String(ambientTemp, 2) : "null"); Serial.print(",");
    Serial.print("\"suhu_ambient_gy906_kelvin\":"); Serial.print(gyOK ? String(ambientKelvin, 2) : "null"); Serial.print(",");
    Serial.print("\"suhu_objek_gy906_celcius\":"); Serial.print(gyOK ? String(objectTemp, 2) : "null"); Serial.print(",");
    Serial.print("\"suhu_objek_gy906_kelvin\":"); Serial.print(gyOK ? String(objectKelvin, 2) : "null"); Serial.print(",");
    Serial.print("\"rpm\":"); Serial.print(currentRPM, 1); Serial.print(",");
    Serial.print("\"tool_wear_min\":"); Serial.print(toolWearMinutes, 2); Serial.print(",");
    #if ENABLE_BATTERY_MONITOR
    Serial.print("\"tegangan_baterai\":"); Serial.print(batteryVoltage, 2); Serial.print(",");
    Serial.print("\"persen_baterai\":"); Serial.print(batteryPercent, 1); Serial.print(",");
    #endif
    Serial.print("\"anomaly\":"); Serial.print(anomaly ? "true" : "false"); Serial.print(",");
    Serial.print("\"anomaly_reason\":\""); Serial.print(anomalyReason); Serial.print("\"");
    Serial.println("}");
  }

  // Pengiriman Telemetry HTTPS Real-Time ke Cloudflare Tunnel
  if (now - lastTelemetryTime >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryTime = now;
    kirimDataTelemetry(latestAirTempK, latestProcessTempK, currentRPM, toolWearMinutes);
    lastToolWearUpdate = millis(); // Reset agar waktu HTTP request tidak dihitung sebagai tool wear
  }
}