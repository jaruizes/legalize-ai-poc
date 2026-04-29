import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { AskRequest, AskResponse, Interview, InterviewSummary } from '../models/chat.model';
import { environment } from '../../environments/environment';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);

  private get baseUrl(): string {
    return environment.apiUrl.replace(/\/ask$/, '');
  }

  ask(request: AskRequest): Observable<AskResponse> {
    return this.http.post<AskResponse>(environment.apiUrl, request);
  }

  getInterview(sessionId: string): Observable<Interview> {
    return this.http.get<Interview>(`${this.baseUrl}/interview/${sessionId}`);
  }

  finalizeInterview(sessionId: string, modelId?: string): Observable<InterviewSummary> {
    return this.http.post<InterviewSummary>(
      `${this.baseUrl}/interview/${sessionId}/summary`,
      modelId ? { model_id: modelId } : {},
    );
  }
}
