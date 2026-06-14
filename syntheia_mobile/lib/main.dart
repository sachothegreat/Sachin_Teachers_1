import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_inappwebview/flutter_inappwebview.dart';

void main() {
  WidgetsFlutterBinding.ensureInitialized();
  // Lock to portrait
  SystemChrome.setPreferredOrientations([
    DeviceOrientation.portraitUp,
    DeviceOrientation.portraitDown,
  ]);
  // Full-screen immersive
  SystemChrome.setEnabledSystemUIMode(SystemUiMode.edgeToEdge);
  runApp(const SyntheiaApp());
}

class SyntheiaApp extends StatelessWidget {
  const SyntheiaApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Syntheia',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF0EA5E9),
          brightness: Brightness.dark,
        ),
        scaffoldBackgroundColor: const Color(0xFF070B14),
        useMaterial3: true,
      ),
      home: const SyntheiaWebView(),
    );
  }
}

class SyntheiaWebView extends StatefulWidget {
  const SyntheiaWebView({super.key});

  @override
  State<SyntheiaWebView> createState() => _SyntheiaWebViewState();
}

class _SyntheiaWebViewState extends State<SyntheiaWebView> {
  // ── Replace with your laptop's local IP ──────────────────────────────────
  // Run `ipconfig getifaddr en0` in Terminal to find it.
  // Make sure your phone and laptop are on the same WiFi network.
  static const String _flaskUrl = 'http://172.23.100.222:5001';
  // ─────────────────────────────────────────────────────────────────────────

  InAppWebViewController? _controller;
  bool _isLoading = true;
  bool _hasError = false;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF070B14),
      body: SafeArea(
        child: Stack(
          children: [
            InAppWebView(
              initialUrlRequest: URLRequest(
                url: WebUri(_flaskUrl),
              ),
              initialSettings: InAppWebViewSettings(
                // Media
                mediaPlaybackRequiresUserGesture: false,
                allowsInlineMediaPlayback: true,
                // JavaScript
                javaScriptEnabled: true,
                // Allow HTTP (mixed content for local network)
                mixedContentMode: MixedContentMode.MIXED_CONTENT_ALWAYS_ALLOW,
                // Disable unnecessary gestures
                allowsBackForwardNavigationGestures: false,
                // Viewport
                useWideViewPort: true,
                loadWithOverviewMode: true,
              ),
              // Grant mic + camera permissions when the page requests them
              onPermissionRequest: (controller, request) async {
                return PermissionResponse(
                  resources: request.resources,
                  action: PermissionResponseAction.GRANT,
                );
              },
              onWebViewCreated: (controller) {
                _controller = controller;
              },
              onLoadStart: (controller, url) {
                setState(() {
                  _isLoading = true;
                  _hasError = false;
                });
              },
              onLoadStop: (controller, url) {
                setState(() {
                  _isLoading = false;
                  _hasError = false;
                });
              },
              onReceivedHttpError: (controller, request, response) {
                if (!(request.isForMainFrame ?? false)) return;
                setState(() {
                  _isLoading = false;
                  _hasError = true;
                });
              },
              onReceivedError: (controller, request, error) {
                if (!(request.isForMainFrame ?? false)) return;
                setState(() {
                  _isLoading = false;
                  _hasError = true;
                });
              },
            ),

            // Loading spinner
            if (_isLoading && !_hasError)
              const Center(
                child: CircularProgressIndicator(
                  color: Color(0xFF0EA5E9),
                ),
              ),

            // Error state — shown when Flask isn't reachable
            if (_hasError)
              Center(
                child: Padding(
                  padding: const EdgeInsets.all(32.0),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.wifi_off,
                          color: Color(0xFF94A3B8), size: 48),
                      const SizedBox(height: 16),
                      const Text(
                        'Cannot reach Syntheia',
                        style: TextStyle(
                          color: Color(0xFFF1F5F9),
                          fontSize: 18,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'Make sure your laptop is running Flask\nand both devices are on the same WiFi.',
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          color: const Color(0xFF94A3B8),
                          fontSize: 14,
                          height: 1.5,
                        ),
                      ),
                      const SizedBox(height: 24),
                      ElevatedButton(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF0EA5E9),
                          foregroundColor: const Color(0xFF04141F),
                          padding: const EdgeInsets.symmetric(
                              horizontal: 32, vertical: 12),
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10),
                          ),
                        ),
                        onPressed: () {
                          setState(() {
                            _isLoading = true;
                            _hasError = false;
                          });
                          _controller?.reload();
                        },
                        child: const Text('Retry',
                            style: TextStyle(fontWeight: FontWeight.w600)),
                      ),
                    ],
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
