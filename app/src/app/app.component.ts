import {
  AfterViewChecked,
  Component,
  computed,
  ElementRef,
  inject,
  signal,
  ViewChild,
} from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { ApiService } from './services/api.service';
import { Message, BedrockModel } from './models/chat.model';
import { environment } from '../environments/environment';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [CommonModule, FormsModule],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent implements AfterViewChecked {
  private apiService = inject(ApiService);
  private sanitizer = inject(DomSanitizer);

  @ViewChild('messagesContainer') messagesContainer!: ElementRef<HTMLDivElement>;
  @ViewChild('inputTextarea') inputTextarea!: ElementRef<HTMLTextAreaElement>;

  messages = signal<Message[]>([]);
  inputValue = '';
  isLoading = signal(false);
  private shouldScroll = false;

  hasMessages = computed(() => this.messages().length > 0);

  readonly ui = environment.ui;
  readonly examples = environment.ui.examples;
  readonly models: BedrockModel[] = environment.ui.models;

  selectedModelId = signal(environment.ui.defaultModelId);
  maxTokens = signal(environment.ui.defaultMaxTokens);
  numResults = signal(environment.ui.defaultNumResults);
  settingsOpen = signal(false);

  systemPrompt = signal(environment.ui.defaultSystemPrompt);

  readonly filterOptions = environment.ui.filterOptions;
  filterRing = signal('');
  filterQuadrant = signal('');
  filterEditions = signal<string[]>([]);

  // Session state — session_id comes from the backend after the first ask
  sessionId = signal<string | null>(null);
  sessionQuestions = signal<string[]>([]);
  sidebarOpen = signal(false);

  // "Finalizar entrevista" state
  summaryLoading = signal(false);
  interviewSummary = signal<string | null>(null);
  showSummaryView = signal(false);

  ngAfterViewChecked(): void {
    if (this.shouldScroll) {
      this.scrollToBottom();
      this.shouldScroll = false;
    }
  }

  private scrollToBottom(): void {
    const el = this.messagesContainer?.nativeElement;
    if (el) el.scrollTop = el.scrollHeight;
  }

  onKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      this.sendMessage();
    }
  }

  autoResize(event: Event): void {
    const el = event.target as HTMLTextAreaElement;
    el.style.height = 'auto';
    el.style.height = Math.min(el.scrollHeight, 180) + 'px';
  }

  private resetTextarea(): void {
    const el = this.inputTextarea?.nativeElement;
    if (el) el.style.height = 'auto';
  }

  sendMessage(): void {
    const question = this.inputValue.trim();
    if (!question || this.isLoading()) return;

    const userMsg: Message = {
      id: crypto.randomUUID(),
      role: 'user',
      content: question,
    };

    const loadingMsg: Message = {
      id: crypto.randomUUID(),
      role: 'assistant',
      content: '',
      loading: true,
    };

    this.messages.update((msgs) => [...msgs, userMsg, loadingMsg]);
    this.sessionQuestions.update((qs) => [...qs, question]);
    this.inputValue = '';
    this.resetTextarea();
    this.isLoading.set(true);
    this.shouldScroll = true;

    const loadingId = loadingMsg.id;

    const filters: Record<string, unknown> = {};
    if (this.filterRing()) filters['ring'] = this.filterRing();
    if (this.filterQuadrant()) filters['quadrant'] = this.filterQuadrant();
    if (this.filterEditions().length) filters['editions'] = this.filterEditions();

    this.apiService.ask({
      question,
      session_id: this.sessionId() ?? undefined,
      model_id: this.selectedModelId(),
      max_tokens: this.maxTokens(),
      num_results: this.numResults(),
      system_prompt: this.systemPrompt(),
      ...(Object.keys(filters).length ? { filters } : {}),
    }).subscribe({
      next: (response) => {
        // Store session_id returned by the backend
        if (response.session_id) {
          this.sessionId.set(response.session_id);
        }
        this.messages.update((msgs) =>
          msgs.map((m) =>
            m.id === loadingId
              ? { ...m, citations: response.citations, showCitations: false, loading: false, content: '' }
              : m,
          ),
        );
        this.animateTyping(loadingId, response.answer);
      },
      error: () => {
        this.messages.update((msgs) =>
          msgs.map((m) =>
            m.id === loadingId
              ? {
                  ...m,
                  content:
                    'Ha ocurrido un error al procesar tu consulta. Por favor, comprueba la conexión e inténtalo de nuevo.',
                  loading: false,
                  error: true,
                }
              : m,
          ),
        );
        this.isLoading.set(false);
        this.shouldScroll = true;
      },
    });
  }

  private animateTyping(messageId: string, fullText: string): void {
    const tokens = fullText.split(/(\s+)/);
    let index = 0;

    const tick = () => {
      if (index >= tokens.length) {
        this.messages.update((msgs) =>
          msgs.map((m) => (m.id === messageId ? { ...m, content: fullText } : m)),
        );
        this.isLoading.set(false);
        this.shouldScroll = true;
        return;
      }
      const next = Math.min(index + 4, tokens.length);
      const revealed = tokens.slice(0, next).join('');
      index = next;
      this.messages.update((msgs) =>
        msgs.map((m) => (m.id === messageId ? { ...m, content: revealed } : m)),
      );
      this.shouldScroll = true;
      setTimeout(tick, 20);
    };

    setTimeout(tick, 20);
  }

  toggleSettings(): void {
    this.settingsOpen.update(v => !v);
  }

  toggleSidebar(): void {
    this.sidebarOpen.update(v => !v);
  }

  toggleEdition(edition: string): void {
    this.filterEditions.update(eds =>
      eds.includes(edition) ? eds.filter(e => e !== edition) : [...eds, edition]
    );
  }

  isEditionSelected(edition: string): boolean {
    return this.filterEditions().includes(edition);
  }

  hasActiveFilters(): boolean {
    return !!(this.filterRing() || this.filterQuadrant() || this.filterEditions().length);
  }

  clearFilters(): void {
    this.filterRing.set('');
    this.filterQuadrant.set('');
    this.filterEditions.set([]);
  }

  selectedModelLabel(): string {
    return this.models.find(m => m.id === this.selectedModelId())?.label ?? this.selectedModelId();
  }

  useExample(example: string): void {
    this.inputValue = example;
    this.sendMessage();
  }

  toggleCitations(messageId: string): void {
    this.messages.update((msgs) =>
      msgs.map((m) =>
        m.id === messageId ? { ...m, showCitations: !m.showCitations } : m,
      ),
    );
  }

  clearChat(): void {
    this.messages.set([]);
    this.sessionId.set(null);
    this.sessionQuestions.set([]);
    this.interviewSummary.set(null);
    this.showSummaryView.set(false);
  }

  shortSessionId(): string {
    const id = this.sessionId();
    if (!id) return '';
    return id.length > 12 ? id.slice(0, 8) + '…' : id;
  }

  scrollToQuestion(index: number): void {
    const container = this.messagesContainer?.nativeElement;
    if (!container) return;
    const questionEls = container.querySelectorAll<HTMLElement>('.msg--question');
    if (questionEls[index]) {
      questionEls[index].scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  }

  getDocumentLabel(source: string): string {
    if (!source) return 'Documento';
    const match = source.match(/\/([^/]+)\/([^/]+?)(?:\.md)?$/);
    if (match) return `${match[1]} › ${match[2]}`;
    const parts = source.split('/');
    return parts[parts.length - 1].replace('.md', '') || source;
  }

  renderContent(raw: string): SafeHtml {
    return this.sanitizer.bypassSecurityTrustHtml(markdownToHtml(raw));
  }

  // ── PDF generation ──────────────────────────────────────────────────────────

  generatePdf(): void {
    const msgs = this.messages();
    const pairs: Array<{ q: string; a: string }> = [];
    for (let i = 0; i < msgs.length - 1; i += 2) {
      if (msgs[i].role === 'user' && msgs[i + 1]?.role === 'assistant' && !msgs[i + 1].loading) {
        pairs.push({ q: msgs[i].content, a: msgs[i + 1].content });
      }
    }
    if (!pairs.length) return;
    openPrintWindow(buildInterviewPrintHtml(this.ui.title, this.shortSessionId(), this.printDate(), pairs));
  }

  printDate(): string {
    return new Date().toLocaleDateString('es-ES', {
      year: 'numeric',
      month: 'long',
      day: 'numeric',
    });
  }

  // ── Finalizar entrevista ────────────────────────────────────────────────────

  finalizeInterview(): void {
    const sid = this.sessionId();
    if (!sid || this.summaryLoading()) return;

    this.summaryLoading.set(true);
    this.interviewSummary.set(null);
    this.showSummaryView.set(true);

    this.apiService.finalizeInterview(sid, this.selectedModelId()).subscribe({
      next: (resp) => {
        this.interviewSummary.set(resp.executive_summary);
        this.summaryLoading.set(false);
      },
      error: () => {
        this.interviewSummary.set(
          'No se pudo generar el informe. Por favor, inténtalo de nuevo.',
        );
        this.summaryLoading.set(false);
      },
    });
  }

  closeSummaryView(): void {
    this.showSummaryView.set(false);
  }

  printSummary(): void {
    const summary = this.interviewSummary();
    if (!summary) return;
    openPrintWindow(buildSummaryPrintHtml(this.ui.title, this.shortSessionId(), this.printDate(), summary));
  }
}

// ---------------------------------------------------------------------------
// Markdown → HTML (no external dependency)
// ---------------------------------------------------------------------------

function markdownToHtml(raw: string): string {
  let text = raw
    .replace(/\s*\(Passage\s+%\[(\d+)\]%[^)]*\)/g, ' <sup class="cite-ref">[$1]</sup>')
    .replace(/%\[(\d+)\]%/g, '<sup class="cite-ref">[$1]</sup>');

  const blocks: string[] = [];
  let inUl = false;
  let inOl = false;

  const closeList = () => {
    if (inUl) { blocks.push('</ul>'); inUl = false; }
    if (inOl) { blocks.push('</ol>'); inOl = false; }
  };

  for (const line of text.split('\n')) {
    const heading = line.match(/^(#{1,4})\s+(.*)/);
    if (heading) {
      closeList();
      const lvl = heading[1].length;
      blocks.push(`<h${lvl}>${inlineMd(heading[2])}</h${lvl}>`);
      continue;
    }

    const ulItem = line.match(/^[*\-]\s+(.*)/);
    if (ulItem) {
      if (inOl) { blocks.push('</ol>'); inOl = false; }
      if (!inUl) { blocks.push('<ul>'); inUl = true; }
      blocks.push(`<li>${inlineMd(ulItem[1])}</li>`);
      continue;
    }

    const olItem = line.match(/^\d+\.\s+(.*)/);
    if (olItem) {
      if (inUl) { blocks.push('</ul>'); inUl = false; }
      if (!inOl) { blocks.push('<ol>'); inOl = true; }
      blocks.push(`<li>${inlineMd(olItem[1])}</li>`);
      continue;
    }

    if (/^---+$/.test(line.trim())) {
      closeList();
      blocks.push('<hr>');
      continue;
    }

    if (line.trim() === '') {
      closeList();
      continue;
    }

    closeList();
    blocks.push(`<p>${inlineMd(line)}</p>`);
  }

  closeList();
  return blocks.join('');
}

function inlineMd(text: string): string {
  return text
    .replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
    .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
    .replace(/__(.+?)__/g, '<strong>$1</strong>')
    .replace(/\*(.+?)\*/g, '<em>$1</em>')
    .replace(/_(.+?)_/g, '<em>$1</em>')
    .replace(/`(.+?)`/g, '<code>$1</code>');
}

// ---------------------------------------------------------------------------
// Print helpers
// ---------------------------------------------------------------------------

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function openPrintWindow(html: string): void {
  const win = window.open('', '_blank', 'width=960,height=720');
  if (!win) return;
  win.document.write(html);
  win.document.close();
}

// Newspaper-style interview PDF
function buildInterviewPrintHtml(
  title: string,
  sessionId: string,
  date: string,
  pairs: Array<{ q: string; a: string }>,
): string {
  const pairsHtml = pairs
    .map(
      ({ q, a }) => `
      <div class="qa-pair">
        <div class="question">${escapeHtml(q)}</div>
        <div class="answer">${markdownToHtml(a)}</div>
      </div>`,
    )
    .join('');

  return `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>${escapeHtml(title)}</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:Georgia,'Times New Roman',serif;font-size:9.5pt;line-height:1.55;color:#111;background:#fff;padding:1.2cm 1.6cm}
  .masthead{display:flex;justify-content:space-between;align-items:baseline;border-top:3px solid #111;border-bottom:1px solid #111;padding:4px 0;margin-bottom:10px;font-size:7pt;letter-spacing:.14em;text-transform:uppercase;font-family:'Arial',sans-serif}
  .kicker{font-size:6.5pt;font-weight:700;text-transform:uppercase;letter-spacing:.22em;color:#8b1c1c;border-bottom:2.5px solid #8b1c1c;padding-bottom:3px;display:inline-block;margin-bottom:6px;font-family:'Arial',sans-serif}
  .headline{font-size:20pt;font-weight:700;line-height:1.1;margin:4px 0 6px;letter-spacing:-.015em}
  .deck{font-size:9pt;font-style:italic;color:#555;border-bottom:2px double #111;padding-bottom:10px;margin-bottom:14px;line-height:1.4}
  .content{columns:2;column-gap:1.3cm;column-rule:.5px solid #bbb}
  .qa-pair{break-inside:avoid;margin-bottom:12px;padding-bottom:12px;border-bottom:.5px solid #ddd}
  .qa-pair:last-child{border-bottom:none}
  .question{font-weight:700;font-style:italic;font-size:10pt;line-height:1.4;margin-bottom:4px;color:#111}
  .question::before{content:'— ';color:#8b1c1c;font-style:normal}
  .answer{font-size:9.5pt;line-height:1.6;text-align:justify;hyphens:auto}
  .answer p{margin-bottom:.45em}.answer p:last-child{margin-bottom:0}
  .answer strong{font-weight:700}.answer em{font-style:italic}
  .answer ul,.answer ol{margin:0 0 .4em 1.3em}.answer li{margin-bottom:.15em}
  .answer h1,.answer h2,.answer h3,.answer h4{font-weight:700;font-size:10pt;margin:.5em 0 .2em}
  .answer code{font-family:monospace;font-size:8.5pt;background:#f5f5f5;padding:0 3px;border-radius:2px}
  .footer{margin-top:14px;border-top:1px solid #111;padding-top:4px;font-size:7pt;color:#888;text-transform:uppercase;letter-spacing:.1em;display:flex;justify-content:space-between;font-family:'Arial',sans-serif}
</style>
</head>
<body>
  <div class="masthead">
    <span>Thoughtworks Technology Radar</span>
    <span>${escapeHtml(date)}</span>
  </div>
  <div class="kicker">Entrevista técnica</div>
  <h1 class="headline">${escapeHtml(title)}</h1>
  <p class="deck">${pairs.length} ${pairs.length === 1 ? 'pregunta' : 'preguntas'}&nbsp;&nbsp;&middot;&nbsp;&nbsp;Sesión ${escapeHtml(sessionId)}</p>
  <div class="content">${pairsHtml}</div>
  <div class="footer">
    <span>${escapeHtml(title)}</span>
    <span>Sesión: ${escapeHtml(sessionId)}</span>
  </div>
  <script>window.addEventListener('load',function(){setTimeout(function(){window.print()},400)})</script>
</body>
</html>`;
}

// Clean executive summary PDF
function buildSummaryPrintHtml(
  title: string,
  sessionId: string,
  date: string,
  summary: string,
): string {
  return `<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Informe — ${escapeHtml(title)}</title>
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{font-family:Georgia,'Times New Roman',serif;font-size:10pt;line-height:1.6;color:#111;background:#fff;padding:1.5cm 2cm}
  .masthead{display:flex;justify-content:space-between;align-items:baseline;border-top:3px solid #111;border-bottom:1px solid #111;padding:4px 0;margin-bottom:12px;font-size:7pt;letter-spacing:.14em;text-transform:uppercase;font-family:'Arial',sans-serif}
  .kicker{font-size:6.5pt;font-weight:700;text-transform:uppercase;letter-spacing:.22em;color:#8b1c1c;border-bottom:2.5px solid #8b1c1c;padding-bottom:3px;display:inline-block;margin-bottom:6px;font-family:'Arial',sans-serif}
  .headline{font-size:22pt;font-weight:700;line-height:1.1;margin:4px 0 6px;letter-spacing:-.015em}
  .deck{font-size:9pt;font-style:italic;color:#555;border-bottom:2px double #111;padding-bottom:10px;margin-bottom:20px;line-height:1.4}
  .content{max-width:100%}
  .content p{margin-bottom:.7em}
  .content p:last-child{margin-bottom:0}
  .content strong{font-weight:700}
  .content em{font-style:italic}
  .content ul,.content ol{margin:.3em 0 .7em 1.4em}
  .content li{margin-bottom:.25em}
  .content h1,.content h2{font-size:13pt;font-weight:700;color:#8b1c1c;margin:1.2em 0 .4em;border-bottom:1px solid #ddd;padding-bottom:3px}
  .content h3,.content h4{font-size:11pt;font-weight:700;margin:.9em 0 .3em}
  .content code{font-family:monospace;font-size:9pt;background:#f5f5f5;padding:0 3px;border-radius:2px}
  .footer{margin-top:24px;border-top:1px solid #111;padding-top:5px;font-size:7pt;color:#888;text-transform:uppercase;letter-spacing:.1em;display:flex;justify-content:space-between;font-family:'Arial',sans-serif}
</style>
</head>
<body>
  <div class="masthead">
    <span>Thoughtworks Technology Radar</span>
    <span>${escapeHtml(date)}</span>
  </div>
  <div class="kicker">Informe ejecutivo</div>
  <h1 class="headline">${escapeHtml(title)}</h1>
  <p class="deck">Sesión ${escapeHtml(sessionId)}&nbsp;&nbsp;&middot;&nbsp;&nbsp;${escapeHtml(date)}</p>
  <div class="content">${markdownToHtml(summary)}</div>
  <div class="footer">
    <span>${escapeHtml(title)}</span>
    <span>Sesión: ${escapeHtml(sessionId)}</span>
  </div>
  <script>window.addEventListener('load',function(){setTimeout(function(){window.print()},400)})</script>
</body>
</html>`;
}
