import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { AskRequest, AskResponse } from '../models/chat.model';
import { environment } from '../../environments/environment';

@Injectable({ providedIn: 'root' })
export class ApiService {
  private http = inject(HttpClient);

  ask(request: AskRequest): Observable<AskResponse> {
    return this.http.post<AskResponse>(environment.apiUrl, request);
  }
}
