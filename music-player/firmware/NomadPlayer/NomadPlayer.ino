// Khan-Nomad music player - step 1: WiFi, song list, MP3 streaming
//
// Joins the Nomad's WiFi, reads the song list from Nomad's index
// (/api/index?path=/Music), streams an MP3 from /media?file=... and decodes it
// in real time. There is no speaker or Bluetooth yet: decoded audio goes to a
// "meter" output that plays at real speed and reports progress and level, so
// we can prove the streaming and decoding work before the hardware arrives.
//
// Step 2 adds the OLED, step 4 swaps the meter for Bluetooth A2DP
// (ESP32-WROOM-32 only; the S3 has no Bluetooth Classic).
// See music-player/README.md.
//
// Board: ESP32 Dev Module (WROOM-32) or ESP32S3 Dev Module (DevKitC-1).
// Libraries: ESP8266Audio 2.4.1, ArduinoJson 7.x.

#include <WiFi.h>
#include <HTTPClient.h>
#include <Preferences.h>
#include <ArduinoJson.h>
#include <vector>
#include "esp_timer.h"
#include "AudioFileSourceHTTPStream.h"
#include "AudioFileSourceBuffer.h"
#include "AudioGeneratorMP3.h"
#include "AudioOutput.h"

// ---------- buttons (to GND, internal pull-ups) ----------
// WROOM-32 pins match docs/ideas/bluetooth-music-player.md; the S3 DevKitC-1
// uses free pins that avoid its strapping, USB and PSRAM pins.
#if CONFIG_IDF_TARGET_ESP32S3
static const uint8_t BTN_PINS[5] = {4, 5, 6, 7, 15};
#else
static const uint8_t BTN_PINS[5] = {32, 33, 25, 26, 27};
#endif
enum { BTN_PLAY, BTN_PREV, BTN_NEXT, BTN_VOL_DOWN, BTN_VOL_UP };
static const char *BTN_NAMES[5] = {"play/pause", "previous", "next", "volume down", "volume up"};

static const size_t MAX_SONGS = 500;
static const uint32_t STREAM_BUFFER = 16 * 1024;

// ---------- settings (saved in flash) ----------
Preferences prefs;
String wifiSsid, wifiPass, nomadHost;
uint16_t nomadPort;

// ---------- a stand-in for the speaker: plays at real speed, measures level ----------
class AudioOutputMeter : public AudioOutput {
 public:
  bool begin() override {
    startUs = esp_timer_get_time();
    samples = 0;
    peak = 0;
    return true;
  }
  bool ConsumeSample(int16_t sample[2]) override {
    // refuse samples that arrive ahead of real time, like a DAC with a full FIFO
    int64_t dueUs = (int64_t)samples * 1000000LL / (hertz ? hertz : 44100);
    if (esp_timer_get_time() - startUs < dueUs) return false;
    samples++;
    int16_t left = Amplify(sample[0]);
    int level = abs((int)left);
    if (level > peak) peak = level;
    return true;
  }
  bool stop() override { return true; }
  void pauseFor(int64_t us) { startUs += us; }   // keep pacing right after a pause
  int takePeak() { int p = peak; peak = 0; return p; }
  uint32_t seconds() const { return hertz ? samples / hertz : 0; }
  uint32_t rate() const { return hertz; }

 private:
  int64_t startUs = 0;
  uint32_t samples = 0;
  int peak = 0;
};

// ---------- player state ----------
std::vector<String> songs;
int current = -1;
bool paused = false;
int64_t pausedAt = 0;
float volume = 0.6f;

AudioFileSourceHTTPStream *httpSrc = nullptr;
AudioFileSourceBuffer *bufferSrc = nullptr;
AudioGeneratorMP3 *mp3 = nullptr;
AudioOutputMeter *out = nullptr;

String baseUrl() {
  return "http://" + nomadHost + (nomadPort == 80 ? "" : ":" + String(nomadPort));
}

String urlEncode(const String &s) {
  static const char *hex = "0123456789ABCDEF";
  String o;
  o.reserve(s.length() * 3);
  for (size_t i = 0; i < s.length(); i++) {
    uint8_t c = (uint8_t)s[i];
    if (isalnum(c) || c == '-' || c == '_' || c == '.' || c == '~' || c == '/') {
      o += (char)c;
    } else {
      o += '%';
      o += hex[c >> 4];
      o += hex[c & 15];
    }
  }
  return o;
}

String songName(int i) {
  String p = songs[i];
  int slash = p.lastIndexOf('/');
  String n = slash >= 0 ? p.substring(slash + 1) : p;
  int dot = n.lastIndexOf('.');
  return dot > 0 ? n.substring(0, dot) : n;
}

// ---------- WiFi ----------
bool connectWifi(uint32_t timeoutMs = 20000) {
  if (WiFi.status() == WL_CONNECTED) return true;
  Serial.printf("[wifi] joining \"%s\"...\n", wifiSsid.c_str());
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);   // power save causes audio dropouts
  WiFi.begin(wifiSsid.c_str(), wifiPass.c_str());
  uint32_t t0 = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - t0 < timeoutMs) delay(250);
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("[wifi] could not join. Check: wifi <ssid> <password>");
    return false;
  }
  Serial.printf("[wifi] connected, IP %s, Nomad at %s\n", WiFi.localIP().toString().c_str(), baseUrl().c_str());
  return true;
}

// ---------- song list from Nomad's index ----------
bool loadSongs() {
  if (!connectWifi()) return false;
  HTTPClient http;
  String url = baseUrl() + "/api/index?path=%2FMusic";
  http.setTimeout(8000);
  if (!http.begin(url)) {
    Serial.println("[songs] bad URL " + url);
    return false;
  }
  int code = http.GET();
  if (code == 202) {
    Serial.println("[songs] Nomad is still building its index, try 'scan' again in a minute");
    http.end();
    return false;
  }
  if (code != 200) {
    Serial.printf("[songs] %s returned %d\n", url.c_str(), code);
    http.end();
    return false;
  }
  songs.clear();
  WiFiClient *stream = http.getStreamPtr();
  stream->setTimeout(3000);
  JsonDocument doc;
  uint32_t lastData = millis();
  while ((http.connected() || stream->available()) && millis() - lastData < 5000) {
    if (!stream->available()) { delay(2); continue; }
    lastData = millis();
    String line = stream->readStringUntil('\n');
    line.trim();
    if (line.isEmpty()) continue;
    if (deserializeJson(doc, line)) continue;
    if (doc["t"] != "f") continue;            // skip the header line and folders
    String path = doc["p"] | "";
    String lower = path;
    lower.toLowerCase();
    if (!lower.endsWith(".mp3")) continue;    // MP3 only for now
    songs.push_back(path);
    if (songs.size() >= MAX_SONGS) break;
  }
  http.end();
  Serial.printf("[songs] %u MP3 songs found\n", (unsigned)songs.size());
  return !songs.empty();
}

// ---------- playback ----------
void stopPlayback() {
  if (mp3) { if (mp3->isRunning()) mp3->stop(); delete mp3; mp3 = nullptr; }
  if (bufferSrc) { delete bufferSrc; bufferSrc = nullptr; }
  if (httpSrc) { delete httpSrc; httpSrc = nullptr; }
  paused = false;
}

void play(int i) {
  if (songs.empty()) { Serial.println("[play] no songs, run 'scan'"); return; }
  if (!connectWifi()) return;
  stopPlayback();
  current = (i % (int)songs.size() + (int)songs.size()) % (int)songs.size();
  String url = baseUrl() + "/media?file=" + urlEncode(songs[current]);
  Serial.printf("[play] %d/%u  %s\n", current + 1, (unsigned)songs.size(), songName(current).c_str());
  httpSrc = new AudioFileSourceHTTPStream(url.c_str());
  httpSrc->SetReconnect(3, 500);
  bufferSrc = new AudioFileSourceBuffer(httpSrc, STREAM_BUFFER);
  mp3 = new AudioGeneratorMP3();
  out->SetGain(volume);
  if (!mp3->begin(bufferSrc, out)) {
    Serial.println("[play] could not start decoding (not an MP3, or the stream failed)");
    stopPlayback();
  }
}

void togglePause() {
  if (!mp3) { play(current < 0 ? 0 : current); return; }
  paused = !paused;
  if (paused) pausedAt = esp_timer_get_time();
  else out->pauseFor(esp_timer_get_time() - pausedAt);
  Serial.println(paused ? "[play] paused" : "[play] resumed");
}

void changeVolume(float delta) {
  volume = constrain(volume + delta, 0.0f, 1.0f);
  out->SetGain(volume);
  Serial.printf("[volume] %d%%\n", (int)roundf(volume * 100));
}

// ---------- buttons ----------
uint8_t btnStable[5], btnLast[5];
uint32_t btnChanged[5];

void pollButtons() {
  for (int b = 0; b < 5; b++) {
    uint8_t v = digitalRead(BTN_PINS[b]);
    if (v != btnLast[b]) { btnLast[b] = v; btnChanged[b] = millis(); }
    if (millis() - btnChanged[b] > 30 && v != btnStable[b]) {
      btnStable[b] = v;
      if (v == LOW) {   // pressed
        Serial.printf("[button] %s\n", BTN_NAMES[b]);
        switch (b) {
          case BTN_PLAY: togglePause(); break;
          case BTN_PREV: play(current - 1); break;
          case BTN_NEXT: play(current + 1); break;
          case BTN_VOL_DOWN: changeVolume(-0.1f); break;
          case BTN_VOL_UP: changeVolume(+0.1f); break;
        }
      }
    }
  }
}

// ---------- serial commands ----------
void printHelp() {
  Serial.println(
      "\nCommands:\n"
      "  list              show the songs\n"
      "  play <n>          play song number n\n"
      "  p                 pause / resume\n"
      "  n / b             next / previous\n"
      "  + / -             volume up / down\n"
      "  status            what's playing\n"
      "  scan              reload the song list\n"
      "  wifi <ssid> <pw>  set the WiFi network (saved)\n"
      "  host <ip[:port]>  set the Nomad address, default 192.168.4.1 (saved)\n"
      "  help              this list\n");
}

void printStatus() {
  Serial.printf("[status] WiFi %s | Nomad %s | songs %u | volume %d%%\n",
                WiFi.status() == WL_CONNECTED ? "connected" : "not connected",
                baseUrl().c_str(), (unsigned)songs.size(), (int)roundf(volume * 100));
  if (mp3 && current >= 0) {
    uint32_t size = httpSrc ? httpSrc->getSize() : 0, pos = httpSrc ? httpSrc->getPos() : 0;
    Serial.printf("[status] %s %s  %u:%02u  %u Hz  downloaded %u/%u KB\n", paused ? "paused" : "playing",
                  songName(current).c_str(), out->seconds() / 60, out->seconds() % 60, out->rate(),
                  pos / 1024, size / 1024);
  }
}

void handleCommand(String cmd) {
  cmd.trim();
  if (cmd.isEmpty()) return;
  String arg;
  int sp = cmd.indexOf(' ');
  if (sp > 0) { arg = cmd.substring(sp + 1); cmd = cmd.substring(0, sp); arg.trim(); }
  cmd.toLowerCase();

  if (cmd == "help" || cmd == "?") printHelp();
  else if (cmd == "list") {
    for (size_t i = 0; i < songs.size(); i++)
      Serial.printf("%3u%s %s\n", (unsigned)(i + 1), (int)i == current ? " >" : "  ", songName(i).c_str());
    if (songs.empty()) Serial.println("(no songs, try 'scan')");
  } else if (cmd == "play") play(arg.length() ? arg.toInt() - 1 : (current < 0 ? 0 : current));
  else if (cmd == "p" || cmd == "pause") togglePause();
  else if (cmd == "n" || cmd == "next") play(current + 1);
  else if (cmd == "b" || cmd == "prev") play(current - 1);
  else if (cmd == "+") changeVolume(+0.1f);
  else if (cmd == "-") changeVolume(-0.1f);
  else if (cmd == "status") printStatus();
  else if (cmd == "scan") loadSongs();
  else if (cmd == "wifi") {
    int sp2 = arg.indexOf(' ');
    wifiSsid = sp2 > 0 ? arg.substring(0, sp2) : arg;
    wifiPass = sp2 > 0 ? arg.substring(sp2 + 1) : "";
    prefs.putString("ssid", wifiSsid);
    prefs.putString("pass", wifiPass);
    stopPlayback();
    WiFi.disconnect(true);
    connectWifi() && loadSongs();
  } else if (cmd == "host") {
    int colon = arg.indexOf(':');
    nomadHost = colon > 0 ? arg.substring(0, colon) : arg;
    nomadPort = colon > 0 ? arg.substring(colon + 1).toInt() : 80;
    prefs.putString("host", nomadHost);
    prefs.putUShort("port", nomadPort);
    Serial.println("[host] Nomad at " + baseUrl());
    loadSongs();
  } else Serial.println("Unknown command, type 'help'");
}

// ---------- main ----------
uint32_t lastStatus = 0;

void setup() {
  Serial.begin(115200);
  delay(300);
  Serial.println("\nKhan-Nomad music player - step 1 (streaming test)");

  prefs.begin("player", false);
  wifiSsid = prefs.getString("ssid", "Khan-Nomad");
  wifiPass = prefs.getString("pass", "password");
  nomadHost = prefs.getString("host", "192.168.4.1");
  nomadPort = prefs.getUShort("port", 80);

  for (int b = 0; b < 5; b++) {
    pinMode(BTN_PINS[b], INPUT_PULLUP);
    btnStable[b] = btnLast[b] = HIGH;
    btnChanged[b] = 0;
  }

  out = new AudioOutputMeter();
  out->SetGain(volume);
  printHelp();
  if (connectWifi()) loadSongs();
}

void loop() {
  if (Serial.available()) handleCommand(Serial.readStringUntil('\n'));
  pollButtons();

  if (mp3 && !paused) {
    if (mp3->isRunning()) {
      if (!mp3->loop()) {
        Serial.println("[play] song finished");
        play(current + 1);
      }
    }
  }

  if (mp3 && !paused && millis() - lastStatus > 3000) {
    lastStatus = millis();
    int peak = out->takePeak();
    int bars = map(peak, 0, 32767, 0, 20);
    Serial.printf("[meter] %u:%02u |%.*s%*s| peak %d\n", out->seconds() / 60, out->seconds() % 60, bars,
                  "####################", 20 - bars, "", peak);
  }
}
