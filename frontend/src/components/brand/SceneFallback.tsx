export type MissingnessChapter = 1 | 2 | 3;

type SceneFallbackProps = { chapter: MissingnessChapter };

export function SceneFallback({ chapter }: SceneFallbackProps) {
  const cells = Array.from({ length: 80 }, (_, index) => {
    const column = index % 10;
    const row = Math.floor(index / 10);
    const isHistory = column >= 7;
    const isWithdrawn = chapter > 1 && isHistory && row >= 2 && row <= 5;
    const x = 157 + column * 29;
    const y = 82 + row * 29;
    return { column, row, isHistory, isWithdrawn, x, y };
  });

  return (
    <svg className="sg-scene-fallback__svg" viewBox="0 0 600 460" role="img" aria-labelledby="sg-scene-title sg-scene-desc">
      <title id="sg-scene-title">The Missingness Register: chapter {chapter}</title>
      <desc id="sg-scene-desc">
        {chapter === 1 && 'A fixed grid of eighty illustrative input marks. The three rightmost columns are labeled history inputs.'}
        {chapter === 2 && 'Twelve history-input marks are displaced from rows three through six. Their empty positions remain outlined. This is a concept, not measured missingness.'}
        {chapter === 3 && 'The displaced history-input marks remain absent from their original slots. Three equal measuring rails represent comparison without a quality ranking.'}
      </desc>
      <path d="M126 49h347v270H126z" className="sg-scene-fallback__plate" />
      <path d="M436 62v240m0-240h13m-13 240h13" className="sg-scene-fallback__bracket" />
      <text x="137" y="34" className="sg-scene-fallback__label">REFERENCE GRID · ILLUSTRATIVE ONLY</text>
      <text x="451" y="75" className="sg-scene-fallback__side-label" transform="rotate(90 451 75)">HISTORY INPUTS</text>
      {cells.map((cell) => cell.isWithdrawn ? (
        <g key={cell.column + '-' + cell.row}>
          <rect x={cell.x} y={cell.y} width="19" height="19" className="sg-scene-fallback__empty" />
          <path d={'M' + (cell.x + 9.5) + ' ' + (cell.y + 9.5) + 'L' + (cell.x + 39.5) + ' ' + (cell.y - 15.5)} className="sg-scene-fallback__connector" />
          <g>
            <path d={'M' + (cell.x + 46) + ' ' + (cell.y - 25) + 'l4 4v15l-4-4zM' + (cell.x + 30) + ' ' + (cell.y - 9) + 'h16l4 4h-16z'} className="sg-scene-fallback__displaced-side" />
            <rect x={cell.x + 30} y={cell.y - 25} width="16" height="16" className="sg-scene-fallback__displaced-face" />
          </g>
        </g>
      ) : (
        <rect
          key={cell.column + '-' + cell.row}
          x={cell.x}
          y={cell.y}
          width="19"
          height="19"
          className={cell.isHistory ? 'sg-scene-fallback__cell sg-scene-fallback__cell--history' : 'sg-scene-fallback__cell'}
        />
      ))}
      <path d="M157 344h232" className="sg-scene-fallback__register-line" />
      <path d="M157 338v12m232-12v12" className="sg-scene-fallback__tick" />
      <text x="157" y="365" className="sg-scene-fallback__axis-label">ORDINARY FEATURES</text>
      {chapter === 3 && (
        <g className="sg-scene-fallback__rails">
          <text x="127" y="395" className="sg-scene-fallback__axis-label">RECORDED COMPARISON</text>
          <path d="M287 389h166M287 407h166M287 425h166" />
          <text x="463" y="393" className="sg-scene-fallback__rail-label">Raw</text>
          <text x="463" y="411" className="sg-scene-fallback__rail-label">Source</text>
          <text x="463" y="429" className="sg-scene-fallback__rail-label">Target</text>
        </g>
      )}
      <path d="M36 80v266m0-266h12m-12 266h12" className="sg-scene-fallback__registration" />
      <circle cx="36" cy="57" r="3" className="sg-scene-fallback__index-dot" />
    </svg>
  );
}
