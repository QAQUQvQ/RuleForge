"""Logical table grid retaining merged cell origins; no source rewriting."""
from html.parser import HTMLParser
from ruleforge.ingestion.evidence import EvidenceError

class GridParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.grid, self.row, self.column, self.cell = {}, -1, 0, None

    def handle_starttag(self, tag, attrs):
        if tag == 'tr':
            self.row += 1
            self.column = 0
        elif tag in ('td', 'th'):
            attrs = dict(attrs)
            self.cell = dict(text='', rowspan=int(attrs.get('rowspan', 1)), colspan=int(attrs.get('colspan', 1)))
        elif tag == 'br' and self.cell is not None:
            self.cell['text'] += ' '

    def handle_data(self, data):
        if self.cell is not None:
            self.cell['text'] += data

    def handle_endtag(self, tag):
        if tag not in ('td', 'th') or self.cell is None:
            return
        while (self.row, self.column) in self.grid:
            self.column += 1
        cell = self.cell
        if not 1 <= cell['rowspan'] <= 100 or not 1 <= cell['colspan'] <= 100:
            raise EvidenceError('unsupported table span')
        cell.update(text=' '.join(cell['text'].split()), origin_row=self.row, origin_column=self.column)
        for r in range(self.row, self.row + cell['rowspan']):
            for c in range(self.column, self.column + cell['colspan']):
                if (r, c) in self.grid:
                    raise EvidenceError('overlapping table cells')
                self.grid[r, c] = dict(cell, row=r, column=c)
        self.column += cell['colspan']
        self.cell = None

def table_grid(text: str) -> list[list[dict]]:
    parser = GridParser()
    parser.feed(text)
    if not parser.grid:
        raise EvidenceError('empty table')
    return [[parser.grid[r, c] for c in sorted(c for rr, c in parser.grid if rr == r)]
            for r in sorted({r for r, _ in parser.grid})]
