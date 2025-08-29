import 'axios';

declare module 'axios' {
  export interface InternalAxiosRequestConfig<D = any> {
    metadata?: { startTime: number };
  }
  export interface AxiosRequestConfig<D = any> {
    metadata?: { startTime: number };
  }
}