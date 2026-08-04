# Projekt-Context

## Adaptive Hydraulic Pump Optimizer (AHPO)

### Version

Projektentwurf V1.1 (ergänzt: Betriebsphasen, InfluxDB-Mapping)

---

# Projektziel

Entwicklung einer HACS-fähigen Home-Assistant-Integration, welche automatisch die optimale Drehzahl einer Primärpumpe (Ladepumpe) in hydraulisch entkoppelten Heizungs- oder Kühlsystemen (Pufferspeicher / hydraulische Weiche) bestimmt.

Die Integration soll vollständig generisch aufgebaut sein und nicht speziell auf NIBE beschränkt werden.

Die Optimierung erfolgt ausschließlich über frei zuweisbare Home-Assistant-Entitäten.

---

# Grundidee

Nicht Temperaturen regeln.

Nicht Spreizungen regeln.

Nicht PI- oder PID-Regelung.

Sondern:

**Online-Optimierung des Systemwirkungsgrades (COP/EER).**

Das Kennfeld liefert lediglich einen optimalen Startwert.

Während des Betriebs wird kontinuierlich weiter optimiert.

---

# Betriebsphasen (neu)

AHPO kennt zwei grundsätzlich unterschiedliche Betriebsphasen. Der Wechsel zwischen ihnen ist notwendig, weil viele Wärmepumpen (z. B. NIBE) die Ladepumpe werkseitig selbst regeln und AHPO diese Regelung nicht ungefragt übersteuern soll.

## Phase A — Passive Lernphase (Shadow Mode)

- AHPO greift **nicht** in die Pumpendrehzahl ein.
- Die native Wärmepumpenregelung (oder eine bestehende externe Steuerung) setzt die Ladepumpendrehzahl selbst.
- AHPO beobachtet ausschließlich: Ist-Drehzahl, Außentemperatur, Verdichterfrequenz, berechnet daraus laufend den COP/EER und befüllt das Kennfeld — exakt wie im aktiven Betrieb, nur ohne eigene Stellaktion.
- Ziel: ein initial belastbares Kennfeld aus real beobachtetem Anlagenverhalten aufbauen, bevor AHPO selbst eingreift.
- Erkennung "externe Steuerung aktiv": entweder über ein optionales, vom Nutzer zugewiesenes Status-Flag/Entity der Wärmepumpe, oder heuristisch über Soll/Ist-Vergleich (falls AHPO in dieser Phase testweise einen Sollwert vorschlägt, ohne ihn zu schreiben, und die tatsächliche Drehzahl systematisch abweicht).
- Confidence-Werte, die in dieser Phase gesammelt werden, sind gleichwertig zu denen aus der aktiven Phase zu behandeln (gleiche Berechnungsvorschrift), da es sich um reale Betriebsdaten handelt.

## Phase B — Aktive Optimierungsphase

- AHPO übernimmt die Stellgröße (Ladepumpendrehzahl) aktiv und führt Hill-Climbing wie beschrieben durch.
- Übergang von Phase A zu Phase B kann granular pro Kennfeldzelle erfolgen (Zelle wird erst aktiv optimiert, sobald ihr Confidence Score einen konfigurierbaren Schwellwert überschreitet) oder global per Service/Konfiguration umgeschaltet werden.
- Empfehlung: pro-Zelle-Freigabe als Standard, zusätzlich ein globaler manueller Override (Service `aktive_phase_aktivieren` / `aktive_phase_deaktivieren`), damit der Nutzer den Umstieg auch erzwingen oder komplett im Shadow Mode bleiben kann.
- Sicherheits-Fallback: Bei Sensorausfall, Fehlerstatus der Wärmepumpe oder Verlust der Schreibberechtigung auf die Pumpenentität fällt AHPO automatisch zurück in Phase A (passiv), statt mit veralteten/fehlerhaften Daten aktiv zu optimieren.
- Neue Entität/Sensor: `Betriebsphase` (Werte: `passiv_lernend`, `aktiv_optimierend`, pro betroffene Kennfeldzelle oder global) — ergänzt die bereits vorgesehene Liste an Ausgabegrößen.

---

# Hauptziel

Maximierung des System-COP (Heizbetrieb)

bzw.

Maximierung des System-EER (Kühlbetrieb)

unter Berücksichtigung der aktuellen Betriebsbedingungen.

---

# Stellgröße

Ladepumpendrehzahl

Einheit:

%

Schrittweite:

1 %

Optional:

Adaptive Grobsuche mit 5 %-Schritten.

Hinweis: Die Stellgröße wird nur in Phase B (aktive Optimierungsphase) tatsächlich geschrieben. In Phase A wird sie ausschließlich gelesen.

---

# Nicht geregelt

Die Sekundärpumpe (Heizkreispumpe) wird nicht beeinflusst.

Sie kann

* konstant laufen
* oder durch ihre eigene Regelung automatisch betrieben werden.

Der Optimierer besitzt immer nur **eine Stellgröße**.

Dadurch bleibt das System stabil und eindeutig optimierbar.

---

# Eingangsgrößen

Pflicht:

* Primär Vorlauf
* Primär Rücklauf
* Primär Volumenstrom
* Elektrische Gesamtleistung des Systems
* Verdichterfrequenz
* Außentemperatur
* Ladepumpendrehzahl (Ist)

Optional:

* Betriebsmodus (Heizen/Kühlen)
* Primärpumpe Ein/Aus
* Verdichterstatus
* Fehlerstatus
* Status "externe Pumpensteuerung aktiv" (für Phase-A-Erkennung)

---

# COP Berechnung

Die Integration berechnet den COP bzw. EER selbstständig.

Keine externe Berechnung notwendig.

Berechnung:

Thermische Leistung

Q = 1.163 × Volumenstrom × DeltaT

DeltaT

Heizen:

VL - RL

Kühlen:

RL - VL

Anschließend

COP = Q / Pel

Pel = elektrische Gesamtleistung des Systems

---

# Kennfeld

Das Kennfeld besitzt drei Dimensionen.

Dimension 1

Außentemperatur

Raster:

2 °C

Dimension 2

Verdichterfrequenz

Raster:

2 Hz

Dimension 3

optimale Ladepumpendrehzahl

Zusätzlich werden gespeichert:

* maximaler COP
* Anzahl Messungen
* Confidence Score
* Zeitstempel letzte Optimierung
* Quelle der Messung (passiv beobachtet / aktiv optimiert) — zur Nachvollziehbarkeit, ohne die Confidence-Berechnung selbst zu unterscheiden

---

# Kennfeldverhalten

Das Kennfeld liefert ausschließlich einen Startwert.

Es regelt niemals direkt.

Beispiel

AT 30°C

Frequenz 42 Hz

↓

Kennfeld

↓

26 %

↓

Online Optimierer startet (nur in Phase B)

↓

26 %

↓

27 %

↓

26 %

↓

Optimales Ergebnis gefunden

↓

Kennfeld wird aktualisiert

---

# Lernstrategie

Kein Überschreiben.

Alle Kennfeldwerte werden gleitend verbessert.

Viele bestätigte Messungen

↓

kleine Änderungen

Wenig Messungen

↓

größere Änderungen möglich

Dies gilt phasenübergreifend: passiv beobachtete und aktiv optimierte Messungen fließen nach derselben Logik in dieselben Kennfeldzellen ein.

---

# Confidence Score

Jeder Kennfeldpunkt erhält eine Vertrauensbewertung.

Speicherung:

* Anzahl erfolgreicher Optimierungen (bzw. valider Beobachtungen in Phase A)
* Streuung der COP-Werte
* Alter der Daten

Neue Punkte:

niedrige Confidence

Alte häufig bestätigte Punkte:

hohe Confidence

Der Confidence-Schwellwert für den Phase-A→Phase-B-Übergang pro Zelle ist konfigurierbar (Default noch zu definieren, z. B. ≥5 valide Messungen und Streuung unter definiertem Grenzwert).

---

# Online Optimierung

Verfahren:

Hill Climbing

mit adaptiver Schrittweite

Kein PI

Kein PID

Kein klassischer Regler

Aktiv nur in Phase B.

---

# Ablauf (Phase B)

1.

Kennfeld liefert Startwert.

2.

Pumpendrehzahl setzen.

3.

Einschwingzeit.

4.

COP mitteln.

5.

Pumpendrehzahl verändern.

6.

COP erneut mitteln.

7.

Verbesserung?

Ja

↓

gleiche Richtung

Nein

↓

Richtung wechseln

8.

Kennfeld aktualisieren.

---

# Ablauf (Phase A)

1.

Ist-Pumpendrehzahl, Außentemperatur, Verdichterfrequenz laufend erfassen.

2.

Einschwingzeit/Stabilitätskriterium prüfen (z. B. Drehzahl seit X Minuten unverändert).

3.

COP mitteln (analog Phase B, ohne eigene Stellaktion).

4.

Kennfeld mit beobachtetem Wertepaar (Drehzahl, COP) aktualisieren.

5.

Confidence Score der betroffenen Zelle erhöhen.

6.

Bei Schwellwertüberschreitung: Zelle für Phase B freigeben.

---

# Zeitablauf

Nach jeder Pumpenänderung (Phase B) bzw. nach erkannter Stabilität (Phase A)

3 Minuten

Einschwingen

anschließend

5 Minuten

COP Mittelwert

Gesamtbewertung

8 Minuten

---

# Adaptive Schrittweite

Normal

1 %

Bei unbekannten Bereichen

2 %

oder

5 %

Kurz vor Optimum

1 %

Nur relevant in Phase B.

---

# Ausgabegrößen

Die Integration stellt sämtliche Werte als Home-Assistant-Entitäten bereit.

Beispiele

Sensoren

* aktueller COP
* gemittelter COP
* thermische Leistung
* aktuelle Pumpendrehzahl
* optimale Pumpendrehzahl
* Kennfeldwert
* Confidence Score
* aktueller Kennfeldindex
* Optimierungsstatus
* Suchrichtung
* letzter Optimierungsschritt
* Anzahl erfolgreicher Optimierungen
* Delta VL
* Delta RL
* Delta T Primär
* Delta T Sekundär (optional)
* Kennfeldtreffer
* Online Optimierung aktiv
* Lernmodus aktiv
* **Betriebsphase (passiv/aktiv, global und/oder pro Zelle)**
* **Anteil aktiv freigegebener Kennfeldzellen**

Alle Sensoren müssen Diagramme in Home Assistant unterstützen.

---

# Home Assistant Funktionen

Konfiguration ausschließlich über Config Flow.

Alle benötigten Entitäten können im UI ausgewählt werden.

Keine YAML-Konfiguration.

---

# Services / Aktionen

Die Integration soll Services bereitstellen.

Beispiele

* Optimierung starten
* Optimierung pausieren
* Optimierung fortsetzen
* Kennfeld exportieren
* Kennfeld importieren
* Kennfeld zurücksetzen
* Confidence zurücksetzen
* Lernmodus aktivieren
* Lernmodus deaktivieren
* **Aktive Phase aktivieren (global oder je Zelle)**
* **Aktive Phase deaktivieren / zurück in passive Lernphase**

Zusätzlich:

Kennfeld als Tabelle abrufen.

Optional:

CSV Export.

Optional:

JSON Export.

---

# Langzeitspeicher

Speicherung

.storage

oder

SQLite

Keine Datenverluste nach Neustart.

Phaseninformation je Kennfeldzelle (passiv/aktiv, Confidence) ist Teil des persistierten Kennfeld-Schemas.

---

# Architektur

GitHub Repository

↓

HACS Integration

↓

Home Assistant

Der Optimierungskern wird vollständig unabhängig von Home Assistant entwickelt.

Dadurch kann er

* simuliert
* getestet
* unit-getestet
* weiterentwickelt

werden.

Die Home-Assistant-Integration bildet lediglich die Schnittstelle.

---

# Projektstruktur

custom_components/

adaptive_hydraulic_optimizer/

* **init**.py
* manifest.json
* config_flow.py
* coordinator.py
* optimizer.py
* learning.py
* cop.py
* interpolation.py
* phase_manager.py (neu — verwaltet Phase-A/Phase-B-Logik pro Kennfeldzelle)
* services.py
* diagnostics.py
* sensor.py
* number.py
* button.py
* select.py
* storage.py
* const.py

---

# Kurzfristiges Projektziel (Phase 1 — Simulation)

Simulation ausschließlich mit historischen InfluxDB-Daten.

Ziele:

* COP berechnen
* Kennfeld erzeugen (inkl. Simulation der passiven Lernphase anhand historischer, extern geregelter Pumpendrehzahlen)
* Online-Optimierung simulieren (Phase B, sobald simuliertes Kennfeld ausreichend Confidence hätte)
* Optimierungsverlauf darstellen
* Grafische Auswertung
* Bewertung der Schrittweiten
* Bewertung der Einschwingzeiten
* Analyse der Konvergenz
* Vergleich verschiedener Optimierungsalgorithmen
* Validierung des Kennfeldes
* Validierung der Phase-A→Phase-B-Übergangslogik (Schwellwert-Sensitivität)

Es erfolgt in Phase 1 keine Verbindung zu Home Assistant.

**Spalten-Mapping (neu):** Da die historischen Daten aus InfluxDB nicht zwangsläufig einheitlich benannt sind, wird im Simulationsskript ein explizites, vom Nutzer vorgegebenes Mapping zwischen InfluxDB-Spalten-/Feldnamen und den logischen Eingangsgrößen (Primär Vorlauf, Primär Rücklauf, Primär Volumenstrom, Elektrische Gesamtleistung, Verdichterfrequenz, Außentemperatur, Ladepumpendrehzahl Ist, optional: Betriebsmodus, Primärpumpe Ein/Aus, Verdichterstatus, Fehlerstatus) benötigt. Kein Hardcoding von Spaltennamen im Code — Mapping erfolgt zentral über eine Konfigurationsstruktur (z. B. Dict oder YAML/JSON-Datei) am Anfang bzw. außerhalb des Skripts.

Die Simulation dient ausschließlich dazu, den Optimierungsalgorithmus sowie die Phasenlogik anhand realer historischer Daten zu entwickeln und zu validieren.

---

# Projektziel Phase 2

Integration des validierten Optimierungskerns als HACS-Integration, inklusive Phase-A/Phase-B-Umschaltlogik.

Alle Sensoren und Stellgrößen werden über frei auswählbare Home-Assistant-Entitäten verbunden.

---

# Langfristiges Ziel

Entwicklung eines universellen, selbstlernenden hydraulischen Pumpenoptimierers für Anlagen mit hydraulischer Entkopplung (Pufferspeicher oder hydraulische Weiche).

Der Optimierer lernt kontinuierlich den optimalen Betriebspunkt in Abhängigkeit von:

* Außentemperatur
* Verdichterfrequenz

und maximiert selbstständig den System-COP bzw. EER — beginnend im passiven Beobachtungsmodus gegenüber einer bestehenden Regelung und übergehend in aktive Eigenregelung, sobald genügend Vertrauen in die gelernten Daten besteht.

Das Kennfeld dient als Langzeitgedächtnis.

Die Online-Optimierung sorgt kontinuierlich für die Feinoptimierung und passt sich automatisch an geänderte Anlagenbedingungen, Alterung und hydraulische Veränderungen an.