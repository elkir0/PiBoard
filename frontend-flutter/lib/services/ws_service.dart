import 'dart:async';
import 'dart:convert';
import 'package:web_socket_channel/web_socket_channel.dart';

/// On the Pi the backend is local (127.0.0.1:8000). Override for a remote
/// preview build with --dart-define=WS_URL=ws://192.168.1.152:8000/ws
const String kWsUrl = String.fromEnvironment('WS_URL', defaultValue: 'ws://127.0.0.1:8000/ws');

/// WebSocket singleton — connects to backend at ws://localhost:8000/ws
class WSService {
  static final WSService _instance = WSService._();
  factory WSService() => _instance;
  WSService._();

  WebSocketChannel? _channel;
  StreamSubscription? _streamSub;
  bool _connected = false;
  Timer? _reconnectTimer;
  Timer? _pingTimer;

  bool get connected => _connected;

  final _messageController = StreamController<Map<String, dynamic>>.broadcast();
  Stream<Map<String, dynamic>> get messages => _messageController.stream;

  final _connectionController = StreamController<bool>.broadcast();
  Stream<bool> get connectionStream => _connectionController.stream;

  void connect() {
    _doConnect();
  }

  void _doConnect() {
    try {
      _streamSub?.cancel();
      _streamSub = null;
      _channel?.sink.close();
      print('[WS] Connecting to $kWsUrl ...');
      _channel = WebSocketChannel.connect(Uri.parse(kWsUrl));

      _channel!.ready.then((_) {
        print('[WS] Connection ready!');
        if (!_connected) {
          _connected = true;
          _connectionController.add(true);
        }
      }).catchError((e) {
        print('[WS] Ready failed: $e');
        _onDisconnect();
      });

      _streamSub = _channel!.stream.listen(
        (raw) {
          try {
            final data = jsonDecode(raw) as Map<String, dynamic>;
            _messageController.add(data);
          } catch (_) {}
          if (!_connected) {
            _connected = true;
            _connectionController.add(true);
          }
        },
        onError: (e) {
          print('[WS] Stream error: $e');
          _onDisconnect();
        },
        onDone: () {
          print('[WS] Stream done (closeCode=${_channel?.closeCode})');
          _onDisconnect();
        },
      );

      // Ping every 30s to keep alive
      _pingTimer?.cancel();
      _pingTimer = Timer.periodic(const Duration(seconds: 30), (_) {
        send({'type': 'ping'});
      });
    } catch (_) {
      _onDisconnect();
    }
  }

  void _onDisconnect() {
    if (_connected) {
      _connected = false;
      _connectionController.add(false);
    }
    _pingTimer?.cancel();
    _reconnectTimer?.cancel();
    _reconnectTimer = Timer(const Duration(seconds: 3), _doConnect);
  }

  void send(Map<String, dynamic> message) {
    try {
      _channel?.sink.add(jsonEncode(message));
    } catch (_) {}
  }

  void dispose() {
    _reconnectTimer?.cancel();
    _pingTimer?.cancel();
    _streamSub?.cancel();
    _channel?.sink.close();
    _messageController.close();
    _connectionController.close();
  }
}
