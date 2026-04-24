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
import { ApiService } from './services/api.service';
import { Message } from './models/chat.model';
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

  @ViewChild('messagesContainer') messagesContainer!: ElementRef<HTMLDivElement>;
  @ViewChild('inputTextarea') inputTextarea!: ElementRef<HTMLTextAreaElement>;

  messages = signal<Message[]>([]);
  inputValue = '';
  isLoading = signal(false);
  private shouldScroll = false;

  hasMessages = computed(() => this.messages().length > 0);

  readonly ui = environment.ui;
  readonly examples = environment.ui.examples;

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
    this.inputValue = '';
    this.resetTextarea();
    this.isLoading.set(true);
    this.shouldScroll = true;

    const loadingId = loadingMsg.id;

    this.apiService.ask({ question }).subscribe({
      next: (response) => {
        this.messages.update((msgs) =>
          msgs.map((m) =>
            m.id === loadingId
              ? {
                  ...m,
                  content: response.answer,
                  citations: response.citations,
                  loading: false,
                  showCitations: false,
                }
              : m,
          ),
        );
        this.isLoading.set(false);
        this.shouldScroll = true;
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
  }

  getDocumentLabel(source: string): string {
    if (!source) return 'Documento';
    // s3://bucket/folder/DOC-ID.md  →  folder › DOC-ID
    const match = source.match(/\/([^/]+)\/([^/]+?)(?:\.md)?$/);
    if (match) return `${match[1]} › ${match[2]}`;
    const parts = source.split('/');
    return parts[parts.length - 1].replace('.md', '') || source;
  }

  getMetadataTitle(message: Message, index: number): string {
    const citation = message.citations?.[index];
    if (!citation) return '';
    const meta = citation.metadata as Record<string, string>;
    return meta?.['title'] ?? meta?.['name'] ?? '';
  }
}
