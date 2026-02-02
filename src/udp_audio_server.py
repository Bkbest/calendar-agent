import socket
import threading
import time
import json
import requests
from io import BytesIO
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional
import wave
from AI_Scope_Agent.basic_agent import graph
import random
import string
from AI_Tools.tools import MyTools


class ClientSession:
    """Manages a client session with buffered audio data"""
    
    def __init__(self, client_address: str, client_port: int):
        self.client_key = f"{client_address}:{client_port}"
        self.client_address = client_address
        self.client_port = client_port
        self.packets: List[bytes] = []
        self.total_size = 0
        self.active = True
        self.last_packet_time = time.time()
        self.processing_scheduled = False  # Track if processing is already scheduled
        self._lock = threading.Lock()
    
    def add_packet(self, packet_data: bytes):
        """Add a packet to the session buffer"""
        with self._lock:
            if self.active:
                self.packets.append(packet_data)
                self.total_size += len(packet_data)
                self.last_packet_time = time.time()
    
    def get_complete_audio_data(self) -> bytes:
        """Get all buffered audio data as a single byte array"""
        with self._lock:
            complete_data = b''.join(self.packets)
            return complete_data
    
    def reset_timeout(self):
        """Reset the timeout timer"""
        self.last_packet_time = time.time()
    
    def is_active(self) -> bool:
        """Check if session is still active (not timed out)"""
        return self.active and (time.time() - self.last_packet_time < 5.0)
    
    def set_processed(self):
        """Mark session as processed"""
        self.active = False
    
    def get_total_size(self) -> int:
        """Get total size of buffered data"""
        return self.total_size


class AudioConversionService:
    """Handles audio conversion and transcription using Eleven Labs API"""
    
    def __init__(self, api_key: str):
        self.api_key = api_key
    
    def is_likely_audio_data(self, data: bytes) -> bool:
        """Check if data is likely audio data"""
        if not data or len(data) < 44:
            return False
        
        # Check for WAV header
        if len(data) >= 12:
            if data[:4] == b'RIFF' and data[8:12] == b'WAVE':
                return True
        
        # Check for MP3 header
        if len(data) >= 3:
            if data[:3] == b'ID3':
                return True
        
        # Check for MP3 sync bytes
        for i in range(len(data) - 3):
            if data[i] == 0xFF and (data[i + 1] & 0xE0) == 0xE0:
                return True
        
        # Assume larger binary data might be raw PCM
        return len(data) > 1000
    
    def convert_to_wav(self, audio_data: bytes, original_format: str = "application/octet-stream") -> bytes:
        """Convert audio data to WAV format"""
        try:
            # Try to detect if it's already WAV
            if len(audio_data) >= 12 and audio_data[:4] == b'RIFF' and audio_data[8:12] == b'WAVE':
                return audio_data
            
            # For raw PCM data, assume 16-bit, 44100 Hz, mono, little-endian
            # This is a simplified conversion - in practice you might want more sophisticated detection
            if len(audio_data) % 2 == 0:  # Assume 16-bit samples
                sample_rate = 44100
                channels = 1
                sample_width = 2
                
                # Create WAV in memory
                wav_buffer = BytesIO()
                with wave.open(wav_buffer, 'wb') as wav_file:
                    wav_file.setnchannels(channels)
                    wav_file.setsampwidth(sample_width)
                    wav_file.setframerate(sample_rate)
                    wav_file.writeframes(audio_data)
                
                wav_buffer.seek(0)
                return wav_buffer.getvalue()
            
            # If we can't convert, return original data
            return audio_data
            
        except Exception as e:
            print(f"[DEBUG] Audio conversion failed: {e}")
            return audio_data
    
    def transcribe_with_eleven_labs(self, wav_data: bytes) -> str:
        """Transcribe audio using Eleven Labs API"""
        try:
            url = "https://api.elevenlabs.io/v1/speech-to-text"
            
            # Prepare multipart form data
            files = {
                'file': ('audio.wav', wav_data, 'audio/wav')
            }
            data = {
                'model_id': 'scribe_v1',
                'language_code': 'en'
            }
            
            headers = {
                'xi-api-key': self.api_key
            }
            
            response = requests.post(url, files=files, data=data, headers=headers)
            
            if response.status_code == 200:
                result = response.json()
                return result.get('text', 'Could not extract transcription')
            else:
                raise Exception(f"API error: {response.status_code} - {response.text}")
                
        except Exception as e:
            print(f"[ERROR] Transcription failed: {e}")
            return f"Transcription failed: {str(e)}"
    
    def convert_and_transcribe(self, audio_data: bytes, original_format: str = "application/octet-stream") -> str:
        """Convert audio to WAV and transcribe it"""
        print("[DEBUG] Converting and transcribing audio")
        
        # Convert to WAV first
        wav_data = self.convert_to_wav(audio_data, original_format)
        
        # Transcribe using Eleven Labs
        transcript = self.transcribe_with_eleven_labs(wav_data)
        
        print(f"[TRANSCRIPTION] {transcript}")
        return transcript


class UdpAudioServer:
    """UDP server that receives audio packets and transcribes them"""
    
    def __init__(self, port: int = 9876, eleven_labs_api_key: str = None):
        self.port = port
        self.server_socket: Optional[socket.socket] = None
        self.executor = ThreadPoolExecutor(max_workers=10)
        self.timeout_executor = ThreadPoolExecutor(max_workers=2)
        self.is_running = False
        self.client_sessions: Dict[str, ClientSession] = {}
        self.audio_service = AudioConversionService(eleven_labs_api_key)
        self._sessions_lock = threading.Lock()
    
    def start_server(self):
        """Start the UDP server"""
        if self.is_running:
            print("[UDP SERVER] Server is already running")
            return
        
        self.executor.submit(self._run_server)
        print("[UDP SERVER] Server startup initiated")
    
    def stop_server(self):
        """Stop the UDP server"""
        print("[UDP SERVER] Initiating shutdown...")
        self.is_running = False
        
        if self.server_socket:
            self.server_socket.close()
        
        # Don't wait for ongoing tasks - shutdown immediately
        with self._sessions_lock:
            self.client_sessions.clear()
        
        # Shutdown executors without waiting
        self.executor.shutdown(wait=False)
        self.timeout_executor.shutdown(wait=False)
        
        print("[UDP SERVER] Server stopped")
    
    def _run_server(self):
        """Main server loop"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.server_socket.bind(('0.0.0.0', self.port))
            self.server_socket.settimeout(1.0)  # Non-blocking with timeout
            self.is_running = True
            
            print(f"[UDP SERVER] Started on port {self.port} - Waiting for connections...")
            
            receive_buffer = bytearray(65536)  # 64KB buffer
            
            while self.is_running:
                try:
                    bytes_received, client_address = self.server_socket.recvfrom_into(receive_buffer)
                    
                    client_key = f"{client_address[0]}:{client_address[1]}"
                    packet_data = bytes(receive_buffer[:bytes_received])
                    
                    print(f"[UDP SERVER] Packet from {client_key} - {bytes_received} bytes")
                    
                    # Handle packet in separate thread (only if server is still running)
                    if self.is_running:
                        try:
                            self.executor.submit(
                                self._handle_packet, 
                                client_key, 
                                packet_data, 
                                client_address[0], 
                                client_address[1]
                            )
                        except RuntimeError as e:
                            if "cannot schedule new futures" in str(e):
                                print("[UDP SERVER] Executor shutdown, ignoring packet")
                                continue
                            raise
                    
                except socket.timeout:
                    # Timeout is normal, continue loop
                    continue
                except Exception as e:
                    if self.is_running:
                        print(f"[UDP SERVER] Error receiving packet: {e}")
                    break
                    
        except Exception as e:
            print(f"[UDP SERVER] Socket error: {e}")
        finally:
            if self.server_socket:
                self.server_socket.close()
            print("[UDP SERVER] Stopped")
    
    def _handle_packet(self, client_key: str, packet_data: bytes, client_address: str, client_port: int):
        """Handle incoming packet from a client"""
        try:
            # Check if server is still running before processing
            if not self.is_running:
                return
            
            # Get or create client session
            with self._sessions_lock:
                if client_key not in self.client_sessions:
                    self.client_sessions[client_key] = ClientSession(client_address, client_port)
                    print(f"[UDP SERVER] New session started for {client_key}")
                
                session = self.client_sessions[client_key]
            
            # Add packet to buffer
            session.add_packet(packet_data)
            print(f"[UDP SERVER] Buffered {len(packet_data)} bytes for {client_key} (total: {session.get_total_size()} bytes)")
            
            # Reset timeout
            session.reset_timeout()
            
            # Schedule processing if no more packets arrive within 2 seconds
            # Only schedule if not already scheduled
            with session._lock:
                if not session.processing_scheduled and self.is_running:
                    try:
                        session.processing_scheduled = True
                        print(f"[DEBUG] Submitting processing task for {client_key}")
                        self.timeout_executor.submit(self._schedule_processing, session)
                    except RuntimeError as e:
                        if "cannot schedule new futures" in str(e):
                            print("[UDP SERVER] Executor shutdown, ignoring packet")
                            session.processing_scheduled = False
                            return
                        raise
                elif session.processing_scheduled:
                    # Skip logging to reduce noise
                    pass
            
            if not self.is_running:
                print(f"[DEBUG] Server not running, not scheduling processing for {client_key}")
            
        except Exception as e:
            print(f"[UDP SERVER] Error handling packet: {e}")
    
    def _schedule_processing(self, session: ClientSession):
        """Schedule processing after timeout"""
        while True:
            # Wait for 2 seconds from last packet
            time.sleep(2.0)
            
            # Check if a new packet arrived during the sleep
            current_time = time.time()
            time_since_last_packet = current_time - session.last_packet_time
            
            if time_since_last_packet >= 2.0:
                # No new packets in the last 2 seconds, process now
                break
            else:
                # New packet arrived, continue waiting
                print(f"[DEBUG] New packet arrived, extending timeout for {session.client_key}")
                continue
        
        # Check if server is still running before processing
        if session.is_active() and self.is_running:
            print(f"[DEBUG] Processing audio for {session.client_key}")
            self._process_complete_audio(session)
        else:
            # Skip logging to reduce noise
            pass
    
    def _process_complete_audio(self, session: ClientSession):
        """Process complete audio data from a session"""
        client_key = session.client_key
        
        if not session.is_active():
            return  # Already processed
        
        try:
            complete_audio_data = session.get_complete_audio_data()
            print(f"[UDP SERVER] Processing complete audio from {client_key} - {len(complete_audio_data)} bytes total")
            
            # Check if it's likely audio data
            if not self.audio_service.is_likely_audio_data(complete_audio_data):
                print(f"[UDP SERVER] Invalid audio data from {client_key} - ignoring")
                self._send_response(session.client_address, session.client_port, b"ERROR: Invalid audio data")
                return
            
            # Convert to WAV format and transcribe
            transcript = self.audio_service.convert_and_transcribe(complete_audio_data, "application/octet-stream")
            
            print(f"[UDP SERVER] Audio transcribed successfully from {client_key} - Original: {len(complete_audio_data)} bytes")
            
            # Send success response with transcript
            response_message = f"SUCCESS: Audio transcribed - {len(transcript)} characters\nTranscript: {transcript}"
            
            # start agent invocation with random thread_id
            random_thread_id = ''.join(random.choices(string.ascii_letters + string.digits, k=8))
            config = {"configurable": {"thread_id": random_thread_id}, "recursion_limit": 50}
            
            # Retry agent invocation up to 2 times on error
            max_retries = 2
            for attempt in range(max_retries + 1):
                try:
                    output = graph.invoke({"messages": transcript,'tools': MyTools().getAllTools()}, config=config)
                    break  # Success, exit retry loop
                except Exception as e:
                    if attempt == max_retries:
                        print(f"[AGENT] Failed after {max_retries + 1} attempts for {client_key}: {e}")
                        raise
                    else:
                        print(f"[AGENT] Attempt {attempt + 1} failed for {client_key}, retrying: {e}")
                        continue
            
            # Send agent response back to client
            if output and 'messages' in output:
                agent_response = output['messages'][-1].content if output['messages'] else "No response"
                response_message = f"SUCCESS: Agent Response: {agent_response}"
            else:
                response_message = f"SUCCESS: Agent Response: No output received"
            
            self._send_response(session.client_address, session.client_port, response_message.encode())
            print(agent_response)
                        
        except Exception as e:
            print(f"[UDP SERVER] Processing error for {client_key}: {e}")
            error_message = f"ERROR: {str(e)}"
            self._send_response(session.client_address, session.client_port, error_message.encode())
        
        finally:
            # Mark session as processed and remove
            session.set_processed()
            with self._sessions_lock:
                if client_key in self.client_sessions:
                    del self.client_sessions[client_key]
            print(f"[UDP SERVER] Session ended for {client_key}")
    
    def _send_response(self, client_address: str, client_port: int, response_data: bytes):
        """Send response to client"""
        try:
            if self.server_socket:
                self.server_socket.sendto(response_data, (client_address, client_port))
        except Exception as e:
            print(f"[UDP SERVER] Error sending response: {e}")
    
    def get_server_port(self) -> int:
        """Get the server port"""
        return self.port if self.server_socket else -1


def main():
    """Main function to run the UDP audio server"""
    # Replace with your actual Eleven Labs API key
    ELEVEN_LABS_API_KEY = "<key>"
    
    server = UdpAudioServer(port=9876, eleven_labs_api_key=ELEVEN_LABS_API_KEY)
    
    try:
        server.start_server()
        print("UDP Audio Server is running. Press Ctrl+C to stop.")
        
        # Keep the main thread alive and handle shutdown gracefully
        while True:
            try:
                time.sleep(1)
            except KeyboardInterrupt:
                print("\nShutdown signal received...")
                break
            
    except KeyboardInterrupt:
        print("\nShutting down server...")
    except Exception as e:
        print(f"Server error: {e}")
    finally:
        server.stop_server()
        print("Server shutdown complete.")


if __name__ == "__main__":
    main()
