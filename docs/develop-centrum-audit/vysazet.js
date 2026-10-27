/**
 * Vysází auditní zprávu do PDF.
 *
 * 1. Vykreslí diagramy (Mermaid) do SVG v `grafy/` — Mermaid se načítá z lokální
 *    kopie `.cache/js/mermaid.min.js` (stáhnout:
 *    curl -o .cache/js/mermaid.min.js https://cdn.jsdelivr.net/npm/mermaid@11.4.1/dist/mermaid.min.js).
 * 2. Otevře `zprava.html` v Chromiu a uloží `docs/develop-centrum-audit.pdf`.
 *
 * Spouštět z kořene repa:  node docs/develop-centrum-audit/vysazet.js
 */
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const KOREN = path.resolve(__dirname, "..", "..");
const TADY = __dirname;
const MERMAID = path.join(KOREN, ".cache", "js", "mermaid.min.js");

const DIAGRAMY = {
  d1_propojeni: `
flowchart TB
  classDef mesto fill:#dce9f8,stroke:#2a78d6,color:#0b0b0b
  classDef firma fill:#fde3d8,stroke:#eb6834,color:#0b0b0b
  classDef osoba fill:#ffffff,stroke:#9a9893,color:#0b0b0b
  classDef cizi fill:#f2f1ee,stroke:#9a9893,color:#0b0b0b
  M["<b>Město Mariánské Lázně</b><br/>IČO 00254061"]:::mesto
  RM["Rada města<br/>= valná hromada firmy<br/>(§ 102 odst. 2 písm. c) ZoO)"]:::mesto
  DC["<b>DEVELOP CENTRUM Mariánské Lázně s.r.o.</b><br/>IČO 61776068, ZK 43 mil. Kč<br/>dříve PARKING CENTRUM a.s."]:::firma
  H["Karel Henych<br/>jednatel od 2023"]:::osoba
  P["RNDr. Pavel Poc<br/>jednatel od 13. 5. 2025<br/>(2023 předseda DR)"]:::osoba
  DR["Dozorčí rada od 4/2025<br/>JUDr. Miloslav Chadim (radní, ANO)<br/>Zdeněk Král (radní, ODS)<br/>Mgr. Ladislav Špelina"]:::osoba
  ST["Martin Hurajčík<br/>starosta, člen DR do 31. 5. 2025"]:::osoba
  ZP["Zahradní a parková spol. s r.o.<br/>IČO 25205978<br/>dodavatel města: 85 smluv, 44,5 mil. Kč"]:::cizi
  SU["skupina SUAS<br/>(Sokolovská uhelná, SUAS GROUP…)<br/>SUAS Commodities: elektřina pro SMS 5 mil. Kč"]:::cizi
  CH["CHEVAK Cheb a.s., Industrial Park Sokolov, MAS 21"]:::cizi
  M -- "100 % podíl" --> DC
  M --- RM
  RM -- "jmenuje, odvolává,<br/>schvaluje závěrku<br/>a zprávu o vztazích" --> DC
  H --- DC
  P --- DC
  DR --- DC
  ST -. "člen DR do 5/2025" .- DC
  P -- "společník + jednatel" --> ZP
  ZP -- "smlouvy 2016–2026" --> M
  P -- "člen orgánů" --> SU
  P -- "člen orgánů" --> CH
  DR -. "radní, kteří jako RM<br/>schvalují smlouvy s firmou" .- RM
`,
  d2_toky_2024: `
flowchart TB
  classDef mesto fill:#dce9f8,stroke:#2a78d6,color:#0b0b0b
  classDef firma fill:#fde3d8,stroke:#eb6834,color:#0b0b0b
  classDef lide fill:#ffffff,stroke:#9a9893,color:#0b0b0b
  R["řidiči<br/>parkovné z 34 automatů<br/>(9,0 mil. Kč v roce 2025)"]:::lide
  M["Město<br/>vlastník pozemků<br/>a (do 5/2025) automatů"]:::mesto
  DC["DEVELOP CENTRUM<br/>správce systému"]:::firma
  N["nákup 10 automatů za 2,1 mil.,<br/>údržba, lidé: osobní náklady<br/>2,1 → 5,7 mil. Kč (2023 → 2024)"]:::firma
  Z["podíl na zisku městu:<br/>0 Kč (2021–2025)"]:::mesto
  R -- "100 % parkovného do rozpočtu města" --> M
  M -- "provize 90 %, čtvrtletně<br/>celkem ~10,7 mil. Kč za 8/2024–12/2025" --> DC
  M -- "prodej 21 automatů<br/>za zůstatkovou 0,46 mil. (5/2025)" --> DC
  DC --> N
  DC -.-> Z
`,
  d3_toky_2026a: `
flowchart TB
  classDef mesto fill:#dce9f8,stroke:#2a78d6,color:#0b0b0b
  classDef firma fill:#fde3d8,stroke:#eb6834,color:#0b0b0b
  classDef lide fill:#ffffff,stroke:#9a9893,color:#0b0b0b
  classDef stat fill:#f2f1ee,stroke:#9a9893,color:#0b0b0b
  R["řidiči"]:::lide
  DC["DEVELOP CENTRUM"]:::firma
  M["Město"]:::mesto
  FU["stát<br/>DPH 21 % z odměny (město si ji zpravidla neodečte)<br/>daň 21 % ze zisku, z něhož se platí záloha"]:::stat
  R -- "100 % parkovného přímo firmě<br/>(od 1. 1. 2026)" --> DC
  M -- "příkazní ROZVOJ: 250 000 Kč bez DPH měsíčně<br/>sjednáno 23. 1. zpětně od 1. 1. 2026" --> DC
  DC -- "záloha na zisk 250 000 Kč měsíčně,<br/>pak čtvrtletně, pak 2 × 750 000 Kč" --> M
  M -- "nájem pozemků pro automaty<br/>(v registru bez ceny)" --> DC
  DC -- "odhadem 0,3–0,7 mil. Kč za pololetí" --> FU
`,
  d4_toky_2026b: `
flowchart TB
  classDef mesto fill:#dce9f8,stroke:#2a78d6,color:#0b0b0b
  classDef firma fill:#fde3d8,stroke:#eb6834,color:#0b0b0b
  classDef lide fill:#ffffff,stroke:#9a9893,color:#0b0b0b
  classDef cizi fill:#f2f1ee,stroke:#9a9893,color:#0b0b0b
  R["řidiči, hotely, nájemci stání,<br/>gastro a ubytování v pavilonech"]:::lide
  M["Město"]:::mesto
  DC["DEVELOP CENTRUM"]:::firma
  I["investice města § 2219:<br/>20 mil. Kč za 9 měsíců 2026<br/>(kolik do půjčených ploch?)"]:::mesto
  V["investice firmy do 500 000 Kč bez DPH<br/>na akci bez souhlasu města;<br/>výnosy zůstávají firmě"]:::firma
  ZSO["Západočeský symfonický orchestr<br/>mimořádná dotace 1,8 mil. Kč (9/2026)"]:::cizi
  M -- "VÝPŮJČKA ZDARMA na 6 let: 34 parkovacích ploch,<br/>Kolonáda Ferdinandova pramene,<br/>pavilony Rudolfova a Lesního pramene" --> DC
  M -- "pojištění vypůjčeného majetku" --> DC
  M --- I
  R -- "parkovné, nájmy stání,<br/>podnájmy, tržby z pavilonů" --> DC
  DC --- V
  DC -- "záloha na zisk 2 × 750 000 Kč<br/>(5/2026, 9/2026)" --> M
  M -- "750 000 Kč ze zálohy<br/>rozpočtovým opatřením" --> ZSO
`,
  d5_casova_osa: `
timeline
  title Jak se přepisovaly peníze mezi městem a firmou
  2020 : město kupuje zbylých 400 akcií od ClickPark za 344 tis. Kč → 100 %
  2023 : změna právní formy a.s. → s.r.o. (duben) : prodej pozemků pod parkovacím domem firmě za 9,76 mil. Kč (srpen)
  2024 : příkazní smlouva na správu parkování, odměna 90 % parkovného (31. 7.) : narovnání sporných nároků 605 tis. Kč (listopad) : příkazní smlouva bydlení (16. 12., účinnost zpětně od 29. 10.)
  2025 : příkazní Nové Centrum (10. 2.) : dozorčí rada → radní Chadim a Král (1. 4.) : prodej 21 automatů firmě za 0,46 mil. (12. 5.) : P. Poc jednatelem (13. 5.) : přejmenování na DEVELOP CENTRUM (13. 6.)
  2026 : dohoda o narovnání, paušál 3 mil./rok + záloha na zisk 3 mil. (23. 1., zpětně od 1. 1.) : rada ukládá připravit snížení základního kapitálu (12. 6.) : ÚOHS k zakázce Třešňovka 190 mil. (29. 7.) : ukončení paušálu zpětně k 30. 6., záloha 1,5 mil. (4. 8.) : výpůjčka zdarma na 6 let (10. 8.)
`,
};

async function vykresliDiagramy(browser) {
  if (!fs.existsSync(MERMAID)) {
    throw new Error(`chybí ${MERMAID}; viz hlavičku skriptu`);
  }
  const page = await browser.newPage();
  await page.setContent(`<!doctype html><html><body></body></html>`);
  await page.addScriptTag({ path: MERMAID });
  await page.evaluate(() => {
    window.mermaid.initialize({
      startOnLoad: false,
      theme: "base",
      fontFamily: "Inter, DejaVu Sans, sans-serif",
      themeVariables: {
        primaryColor: "#f2f1ee",
        primaryBorderColor: "#9a9893",
        primaryTextColor: "#0b0b0b",
        lineColor: "#52514e",
        fontSize: "13px",
        cScale0: "#dce9f8", cScale1: "#fde3d8", cScale2: "#e3f5ee", cScale3: "#fff1cf",
        cScale4: "#f2f1ee", cScale5: "#dce9f8", cScale6: "#fde3d8",
      },
      flowchart: { htmlLabels: false, curve: "basis", nodeSpacing: 30, rankSpacing: 40, wrappingWidth: 260 },
      timeline: { disableMulticolor: false },
    });
  });
  for (const [jmeno, def] of Object.entries(DIAGRAMY)) {
    const svg = await page.evaluate(async ([id, d]) => {
      const out = await window.mermaid.render(id, d.trim());
      return out.svg;
    }, [jmeno, def]);
    fs.writeFileSync(path.join(TADY, "grafy", `${jmeno}.svg`), svg);
    console.log("   diagram", jmeno);
  }
  await page.close();
}

async function vysazejPdf(browser) {
  // Diagramy se vkládají do stránky přímo (inline SVG): přes <img> Chromium
  // SVG z Mermaidu nenačte.
  let html = fs.readFileSync(path.join(TADY, "zprava.html"), "utf8");
  html = html.replace(/<img src="grafy\/(d\d_[a-z0-9_]+)\.svg"[^>]*>/g, (_, jmeno) => {
    const svg = fs.readFileSync(path.join(TADY, "grafy", `${jmeno}.svg`), "utf8");
    return `<div class="inline-svg">${svg}</div>`;
  });
  const docasny = path.join(TADY, ".zprava.vysazena.html");
  fs.writeFileSync(docasny, html);
  const page = await browser.newPage();
  await page.goto("file://" + docasny, { waitUntil: "load" });
  await page.emulateMedia({ media: "print" });
  const cil = path.join(KOREN, "docs", "develop-centrum-audit.pdf");
  await page.pdf({
    path: cil,
    format: "A4",
    printBackground: true,
    margin: { top: "18mm", bottom: "18mm", left: "16mm", right: "16mm" },
    displayHeaderFooter: true,
    headerTemplate: `<div></div>`,
    footerTemplate: `<div style="font-family: Inter, 'DejaVu Sans', sans-serif; font-size: 8px; color: #52514e; width: 100%; padding: 0 16mm; display: flex; justify-content: space-between;">
      <span>DEVELOP CENTRUM Mariánské Lázně s.r.o. · auditní zpráva z veřejných zdrojů · stav k 27. 10. 2026</span>
      <span>strana <span class="pageNumber"></span> / <span class="totalPages"></span></span></div>`,
  });
  console.log("   PDF →", cil, Math.round(fs.statSync(cil).size / 1024), "kB");
  await page.close();
  fs.unlinkSync(docasny);
}

(async () => {
  const browser = await chromium.launch();
  try {
    console.log("diagramy:");
    await vykresliDiagramy(browser);
    console.log("pdf:");
    await vysazejPdf(browser);
  } finally {
    await browser.close();
  }
})().catch((e) => { console.error(e); process.exit(1); });
