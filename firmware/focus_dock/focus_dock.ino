// Прошивка подставки «Фокус-док» для ESP32.
// Протокол — firmware/PROTOCOL.md (115200 бод, строки с '\n').
//
// Железо:
//   - датчик Холла (например, A3144 или модуль KY-003) — магнит в чехле/подставке;
//   - кольцо WS2812 (библиотека Adafruit_NeoPixel);
//   - DFPlayer Mini + динамик (библиотека DFRobotDFPlayerMini), mp3 на microSD;
//   - одна кнопка: короткое нажатие — пауза, долгое — режим «пишу в тетради».
//
// Библиотеки (Arduino IDE → Управление библиотеками):
//   "Adafruit NeoPixel", "DFRobotDFPlayerMini".

#include <Adafruit_NeoPixel.h>
#include <DFRobotDFPlayerMini.h>

// ---------------- Пины и параметры (поменяй под свою плату) ----------------
const int PIN_HALL = 27;          // выход датчика Холла
const bool HALL_ACTIVE_LOW = true; // A3144/KY-003 дают LOW, когда магнит рядом
const int PIN_BUTTON = 26;        // кнопка на GND, используем INPUT_PULLUP
const int PIN_LEDS = 25;          // DIN кольца WS2812
const int LED_COUNT = 12;         // сколько светодиодов в кольце
const int LED_BRIGHTNESS = 60;    // 0..255, не слепим глаза
const int PIN_DF_RX = 16;         // RX ESP32 ← TX DFPlayer
const int PIN_DF_TX = 17;         // TX ESP32 → RX DFPlayer (через резистор 1 кОм)
const int DF_VOLUME = 18;         // громкость DFPlayer 0..30

const char* FW_VERSION = "0.1";
const unsigned long DEBOUNCE_MS = 300;    // антидребезг датчика телефона
const unsigned long BUTTON_DEBOUNCE_MS = 30;
const unsigned long LONG_PRESS_MS = 1000; // долгое нажатие
const unsigned long BLINK_MS = 400;       // период мигания BLINK_RED

// ---------------- Глобальные объекты ----------------
Adafruit_NeoPixel ring(LED_COUNT, PIN_LEDS, NEO_GRB + NEO_KHZ800);
HardwareSerial dfSerial(2);
DFRobotDFPlayerMini dfPlayer;
bool dfReady = false;

// Датчик телефона
bool dockedStable = false;        // подтверждённое состояние
bool dockedRaw = false;           // последнее прочитанное
unsigned long dockChangedAt = 0;  // когда сырое значение поменялось

// Кнопка
bool buttonDown = false;
bool longSent = false;
unsigned long buttonDownAt = 0;
unsigned long buttonChangedAt = 0;

// Светодиоды
enum LedMode { MODE_OFF, MODE_SOLID, MODE_BLINK };
LedMode ledMode = MODE_OFF;
uint32_t ledColor = 0;
bool blinkOn = false;
unsigned long lastBlinkAt = 0;

// Входящая строка с ПК
String inputLine;

// ---------------- Светодиоды ----------------
void fillRing(uint32_t color) {
  for (int i = 0; i < LED_COUNT; i++) ring.setPixelColor(i, color);
  ring.show();
}

void setLed(const String& name) {
  if (name == "GREEN")       { ledMode = MODE_SOLID; ledColor = ring.Color(0, 200, 40); }
  else if (name == "YELLOW") { ledMode = MODE_SOLID; ledColor = ring.Color(230, 160, 0); }
  else if (name == "RED")    { ledMode = MODE_SOLID; ledColor = ring.Color(230, 20, 10); }
  else if (name == "BLUE")   { ledMode = MODE_SOLID; ledColor = ring.Color(20, 90, 230); }
  else if (name == "BLINK_RED") { ledMode = MODE_BLINK; ledColor = ring.Color(230, 20, 10); }
  else if (name == "OFF")    { ledMode = MODE_OFF; ledColor = 0; }
  else return;  // неизвестный цвет — игнорируем

  if (ledMode == MODE_BLINK) {
    blinkOn = true;
    lastBlinkAt = millis();
    fillRing(ledColor);
  } else {
    fillRing(ledMode == MODE_OFF ? 0 : ledColor);
  }
}

void updateBlink() {
  if (ledMode != MODE_BLINK) return;
  if (millis() - lastBlinkAt >= BLINK_MS) {
    lastBlinkAt = millis();
    blinkOn = !blinkOn;
    fillRing(blinkOn ? ledColor : 0);
  }
}

// ---------------- Звук ----------------
void playSound(int n) {
  if (!dfReady || n < 1 || n > 255) return;
  dfPlayer.playMp3Folder(n);  // файл /mp3/000n.mp3
}

// ---------------- Датчик телефона ----------------
bool readHall() {
  bool level = digitalRead(PIN_HALL);
  return HALL_ACTIVE_LOW ? (level == LOW) : (level == HIGH);
}

void sendDock() {
  Serial.print("DOCK ");
  Serial.println(dockedStable ? "1" : "0");
}

void updateDock() {
  bool now = readHall();
  if (now != dockedRaw) {           // сырое значение поменялось — запускаем таймер
    dockedRaw = now;
    dockChangedAt = millis();
  }
  // Считаем изменение настоящим, только если оно держится DEBOUNCE_MS.
  if (dockedRaw != dockedStable && millis() - dockChangedAt >= DEBOUNCE_MS) {
    dockedStable = dockedRaw;
    sendDock();
  }
}

// ---------------- Кнопка ----------------
void updateButton() {
  bool pressed = digitalRead(PIN_BUTTON) == LOW;
  if (pressed == buttonDown || millis() - buttonChangedAt < BUTTON_DEBOUNCE_MS) {
    // Держим кнопку: долгое нажатие отправляем сразу, не дожидаясь отпускания.
    if (buttonDown && !longSent && millis() - buttonDownAt >= LONG_PRESS_MS) {
      longSent = true;
      Serial.println("BTN NOTEBOOK");
    }
    return;
  }
  buttonChangedAt = millis();
  buttonDown = pressed;
  if (pressed) {
    buttonDownAt = millis();
    longSent = false;
  } else if (!longSent) {
    Serial.println("BTN PAUSE");   // отпустили быстро — короткое нажатие
  }
}

// ---------------- Команды с ПК ----------------
void handleCommand(String line) {
  line.trim();
  if (line.length() == 0) return;
  if (line.startsWith("LED ")) {
    setLed(line.substring(4));
  } else if (line.startsWith("SOUND ")) {
    playSound(line.substring(6).toInt());
  } else if (line == "PING") {
    Serial.println("PONG");
  } else if (line == "STATUS") {
    sendDock();
  }
  // Остальное молча игнорируем.
}

void readSerial() {
  while (Serial.available() > 0) {
    char c = (char)Serial.read();
    if (c == '\n') {
      handleCommand(inputLine);
      inputLine = "";
    } else if (c != '\r' && inputLine.length() < 64) {
      inputLine += c;
    }
  }
}

// ---------------- setup / loop ----------------
void setup() {
  Serial.begin(115200);
  pinMode(PIN_HALL, INPUT_PULLUP);
  pinMode(PIN_BUTTON, INPUT_PULLUP);

  ring.begin();
  ring.setBrightness(LED_BRIGHTNESS);
  fillRing(0);

  dfSerial.begin(9600, SERIAL_8N1, PIN_DF_RX, PIN_DF_TX);
  dfReady = dfPlayer.begin(dfSerial);   // без DFPlayer подставка всё равно работает
  if (dfReady) dfPlayer.volume(DF_VOLUME);

  dockedRaw = dockedStable = readHall();
  Serial.print("HELLO fw=");
  Serial.println(FW_VERSION);
  sendDock();
}

void loop() {
  readSerial();
  updateDock();
  updateButton();
  updateBlink();
  delay(5);
}
