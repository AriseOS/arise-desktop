export interface User {
  id: number;
  username: string;
  email: string;
  full_name?: string;
  is_active: boolean;
  created_at: string;
}

export interface AuthResponse {
  access_token: string;
  token_type: string;
  user: User;
}

export interface ChatMessage {
  id: string;
  message: string;
  response: string;
  timestamp: Date;
  session_id: string;
}

export interface ApiError {
  detail: string;
}