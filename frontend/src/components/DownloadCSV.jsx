// Cells starting with these characters are interpreted as formulas by Excel /
// Sheets (CSV injection), so they are prefixed with an apostrophe.
const FORMULA_PREFIX = /^[=+\-@\t\r]/;

// RFC 4180 field escaping: quote when the value has a comma, quote, CR or LF,
// and double any embedded quotes. Formula-looking text is neutralized first.
function escapeCsvCell(value) {
  if (value === null || value === undefined) return "";
  let text = String(value);
  if (typeof value === "string" && FORMULA_PREFIX.test(text)) {
    text = `'${text}`;
  }
  if (/[",\r\n]/.test(text)) {
    return `"${text.replace(/"/g, '""')}"`;
  }
  return text;
}

function buildRosterCsv(data) {
  const { rounds, court_numbers } = data;
  const maxResting = Math.max(...rounds.map((r) => r.resting.length), 0);

  const header = ["Round", "Court", "TeamA1", "TeamA2", "TeamB1", "TeamB2"];
  for (let i = 1; i <= maxResting; i++) header.push(`Rest${i}`);

  const rows = [header.map(escapeCsvCell).join(",")];

  for (const round of rounds) {
    const restCells = [...round.resting];
    while (restCells.length < maxResting) restCells.push("");

    round.courts.forEach((court, ci) => {
      const row = [
        round.round,
        court_numbers?.[ci] ?? ci + 1,
        court.team_a[0],
        court.team_a[1],
        court.team_b[0],
        court.team_b[1],
        ...restCells,
      ];
      rows.push(row.map(escapeCsvCell).join(","));
    });
  }

  // RFC 4180 line endings, with a UTF-8 BOM so Excel reads non-ASCII names correctly.
  return `\uFEFF${rows.join("\r\n")}`;
}

export default function DownloadCSV({ data }) {
  if (!data) return null;

  function download() {
    const blob = new Blob([buildRosterCsv(data)], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "roster.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <button
      onClick={download}
      className="inline-flex items-center gap-2 px-4 py-2.5 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 transition-colors"
    >
      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 10v6m0 0l-3-3m3 3l3-3M3 17V7a2 2 0 012-2h6l2 2h6a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2z" />
      </svg>
      Download CSV
    </button>
  );
}
