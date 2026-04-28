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

  // System prompt — editable by user, defaults to the prompt defined in environment
  systemPrompt = signal(environment.ui.defaultSystemPrompt);

  readonly filterOptions = environment.ui.filterOptions;
  filterRing = signal('');
  filterQuadrant = signal('');
  filterEditions = signal<string[]>([]);

  // Session state
  sessionId = signal<string | null>(null);
  sessionQuestions = signal<string[]>([]);
  sidebarOpen = signal(false);

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
    // Generate a local session ID on the first message of each conversation.
    // It is display-only — Bedrock sessions are not used.
    if (!this.sessionId()) {
      this.sessionId.set(crypto.randomUUID());
    }
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
      model_id: this.selectedModelId(),
      max_tokens: this.maxTokens(),
      num_results: this.numResults(),
      system_prompt: this.systemPrompt(),
      ...(Object.keys(filters).length ? { filters } : {}),
    }).subscribe({
      next: (response) => {
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
  }

  shortSessionId(): string {
    const id = this.sessionId();
    if (!id) return '';
    return id.length > 12 ? id.slice(0, 8) + '…' : id;
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
