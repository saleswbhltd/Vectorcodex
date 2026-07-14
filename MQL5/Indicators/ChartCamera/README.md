# ChartCamera – rövid használati útmutató

A **ChartCamera** egy MetaTrader 5 indikátor, amely automatikusan képernyőképet készít az új kereskedések nyitásakor és zárásakor. A PNG kép mellé opcionálisan JSON-metaadatot és egy összesítő CSV-fájlt is ment.

## Telepítés

1. Töltsd le a [`ChartCamera.mq5`](./ChartCamera.mq5) fájlt.
2. Az MT5-ben válaszd a **Fájl → Adatmappa megnyitása** menüpontot.
3. Másold a fájlt ide: `MQL5\Indicators\ChartCamera\`.
4. Nyisd meg MetaEditorban, majd fordítsd le az **F7** billentyűvel.
5. Az MT5 Navigátorában frissítsd az indikátorokat, majd húzd a **ChartCamera** indikátort egy chartra.

## Használat

- Hagyd az indikátort a charton; alapbeállítással másodpercenként ellenőrzi az új ügyleteket.
- A nyitási és zárási eseményekről automatikusan képet készít.
- Ha az `InpUseTradeSymbolChart` értéke `true`, legyen nyitva az ügylet szimbólumához tartozó chart. Az indikátor először azonos idősíkú chartot keres, majd bármely nyitott, megfelelő szimbólumú chartot használ.
- Alapbeállítással az indulás előtti régi ügyleteket nem fényképezi le.

## Fontos beállítások

| Beállítás | Jelentés |
|---|---|
| `InpTimerSeconds` | Az ellenőrzés gyakorisága másodpercben. |
| `InpCaptureOpenDeals` | Kép készítése ügyletnyitáskor. |
| `InpCaptureCloseDeals` | Kép készítése ügyletzáráskor. |
| `InpUseTradeSymbolChart` | Az ügylet szimbólumának nyitott chartját használja. |
| `InpImageWidth`, `InpImageHeight` | A mentett PNG mérete. |
| `InpWriteJson` | JSON-metaadat mentése a kép mellé. |
| `InpWriteIndexCsv` | Az események hozzáfűzése az `index.csv` fájlhoz. |
| `InpCaptureExistingHistoryOnStart` | A már létező előzmények feldolgozása induláskor. |
| `InpTerminalWideDedup` | Ugyanazon ügylet többszöri mentésének megakadályozása. |

## Mentési hely

Élő vagy demó terminálban:

```text
MQL5\Files\ChartCamera\LIVE\<számlaszám>\<szimbólum>_P<idősík>\
```

Stratégiai tesztelőben:

```text
<Tester Agent>\MQL5\Files\ChartCamera\TEST_NON6E\<számlaszám>\<szimbólum>_P<idősík>\
```

A mappában a képek `.png`, a metaadatok `.json`, az összesített eseménylista pedig `index.csv` formátumban található.

## Hibaelhárítás

Ha nem készül kép, ellenőrizd az MT5 **Experts** és **Journal** naplóját. Az `InpUseTradeSymbolChart=true` beállítás mellett győződj meg arról is, hogy az ügylet szimbólumának chartja nyitva van.
