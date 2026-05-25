import React, { useState, useEffect, useRef, useMemo } from 'react';
import {
  StyleSheet,
  Text,
  View,
  TouchableOpacity,
  TextInput,
  ScrollView,
  SafeAreaView,
  StatusBar,
  PermissionsAndroid,
  Platform,
  Dimensions,
} from 'react-native';
import { Room, RoomEvent, Participant } from 'livekit-client';
import { AudioSession } from '@livekit/react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withRepeat,
  withTiming,
  withSpring,
  cancelAnimation,
  Easing,
  interpolateColor,
  useDerivedValue,
} from 'react-native-reanimated';

// Get device width
const { width } = Dimensions.get('window');

// Status types
type AgentStatus = 'disconnected' | 'connecting' | 'connected' | 'listening' | 'speaking';

// Message structure
interface ChatMessage {
  id: string;
  sender: 'user' | 'bot';
  text: string;
}

// UTF-8 Helper to safely decode Telugu characters from bytes
function decodeUTF8(bytes: Uint8Array): string {
  try {
    if (typeof TextDecoder !== 'undefined') {
      return new TextDecoder().decode(bytes);
    }
  } catch (e) { }

  let out = '', i = 0, len = bytes.length;
  while (i < len) {
    let c = bytes[i++];
    switch (c >> 4) {
      case 0: case 1: case 2: case 3: case 4: case 5: case 6: case 7:
        out += String.fromCharCode(c);
        break;
      case 12: case 13:
        out += String.fromCharCode(((c & 0x1F) << 6) | (bytes[i++] & 0x3F));
        break;
      case 14:
        out += String.fromCharCode(
          ((c & 0x0F) << 12) |
          ((bytes[i++] & 0x3F) << 6) |
          ((bytes[i++] & 0x3F) << 0)
        );
        break;
    }
  }
  return out;
}

export default function VoiceAgentScreen() {
  // Config states
  const [serverUrl, setServerUrl] = useState<string>('http://10.212.35.70:8000'); // Default to emulator gateway IP
  const [showSettings, setShowSettings] = useState<boolean>(false);

  // Connection & Room states
  const [status, setStatus] = useState<AgentStatus>('disconnected');
  const [error, setError] = useState<string | null>(null);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [persona, setPersona] = useState<'prank' | 'support' | 'real_estate'>('support');

  // Ref to store the LiveKit Room object
  const roomRef = useRef<Room | null>(null);
  const scrollViewRef = useRef<ScrollView>(null);

  // Shared values for Reanimated orb
  const scale = useSharedValue(1);
  const glowOpacity = useSharedValue(0.4);
  const rotation = useSharedValue(0);

  // Request Android Microphone Permission
  const requestMicrophonePermission = async () => {
    if (Platform.OS === 'android') {
      try {
        const granted = await PermissionsAndroid.request(
          PermissionsAndroid.PERMISSIONS.RECORD_AUDIO,
          {
            title: 'Microphone Permission',
            message: 'Telugu Voice Agent needs microphone access to hear you speak.',
            buttonNeutral: 'Ask Me Later',
            buttonNegative: 'Cancel',
            buttonPositive: 'OK',
          }
        );
        return granted === PermissionsAndroid.RESULTS.GRANTED;
      } catch (err) {
        console.warn(err);
        return false;
      }
    }
    return true; // iOS permission handled via infoPlist Info.plist configuration
  };

  // Setup animations depending on agent status
  useEffect(() => {
    // Reset animations
    cancelAnimation(scale);
    cancelAnimation(glowOpacity);
    cancelAnimation(rotation);

    if (status === 'disconnected') {
      // Slow breathing animation
      scale.value = withRepeat(withTiming(1.05, { duration: 2500, easing: Easing.ease }), -1, true);
      glowOpacity.value = withRepeat(withTiming(0.2, { duration: 2500 }), -1, true);
      rotation.value = 0;
    } else if (status === 'connecting') {
      // Rapid pulse & rotate spinner
      scale.value = withRepeat(withTiming(1.15, { duration: 600, easing: Easing.ease }), -1, true);
      glowOpacity.value = withRepeat(withTiming(0.6, { duration: 600 }), -1, true);
      rotation.value = withRepeat(withTiming(360, { duration: 2000, easing: Easing.linear }), -1, false);
    } else if (status === 'connected') {
      // Gentle ready pulse
      scale.value = withRepeat(withTiming(1.1, { duration: 1800, easing: Easing.ease }), -1, true);
      glowOpacity.value = withRepeat(withTiming(0.4, { duration: 1800 }), -1, true);
      rotation.value = 0;
    } else if (status === 'listening') {
      // Stable large scale with high glow (active listening)
      scale.value = withSpring(1.25);
      glowOpacity.value = withRepeat(withTiming(0.7, { duration: 800 }), -1, true);
      rotation.value = 0;
    } else if (status === 'speaking') {
      // Rapid wave audio simulation
      scale.value = withRepeat(withTiming(1.3, { duration: 300, easing: Easing.ease }), -1, true);
      glowOpacity.value = withRepeat(withTiming(0.8, { duration: 300 }), -1, true);
      rotation.value = 0;
    }
  }, [status]);

  // Derived color value for animated orb
  const animatedColorValue = useDerivedValue(() => {
    if (status === 'disconnected') return 0;
    if (status === 'connecting') return 1;
    if (status === 'connected') return 2;
    if (status === 'listening') return 3;
    return 4; // 'speaking'
  });

  // Animated styles
  const animatedOrbStyle = useAnimatedStyle(() => {
    // Interpolate glowing color based on status
    const backgroundColor = interpolateColor(
      animatedColorValue.value,
      [0, 1, 2, 3, 4],
      [
        'rgba(99, 102, 241, 0.9)',  // Disconnected: Soft Indigo/Blue
        'rgba(245, 158, 11, 0.9)',  // Connecting: Amber/Orange
        'rgba(6, 182, 212, 0.9)',   // Connected Ready: Cyan
        'rgba(236, 72, 153, 0.9)',  // User Speaking: Hot Pink/Magenta
        'rgba(16, 185, 129, 0.9)',  // Agent Speaking: Emerald Green
      ]
    );

    return {
      transform: [
        { scale: scale.value },
        { rotate: `${rotation.value}deg` }
      ],
      backgroundColor,
    };
  });

  const animatedGlowStyle = useAnimatedStyle(() => {
    const shadowColor = interpolateColor(
      animatedColorValue.value,
      [0, 1, 2, 3, 4],
      [
        'rgb(99, 102, 241)',  // Disconnected: Indigo
        'rgb(245, 158, 11)',  // Connecting: Amber
        'rgb(6, 182, 212)',   // Connected: Cyan
        'rgb(236, 72, 153)',  // Listening: Pink
        'rgb(16, 185, 129)',  // Speaking: Green
      ]
    );

    return {
      transform: [{ scale: scale.value * 1.3 }],
      opacity: glowOpacity.value,
      borderColor: shadowColor,
    };
  });

  // Connect to the backend and establish LiveKit session
  const connectSession = async () => {
    setError(null);
    setStatus('connecting');
    setMessages([]);

    const hasMicPermission = await requestMicrophonePermission();
    if (!hasMicPermission) {
      setError('Microphone permission is required to talk.');
      setStatus('disconnected');
      return;
    }

    try {
      // 1. Fetch connection details from the FastAPI backend
      const response = await fetch(`${serverUrl}/connect`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({ persona }),
      });

      if (!response.ok) {
        throw new Error(`Backend returned error code: ${response.status}`);
      }

      const connectionInfo = await response.json();
      const { url, token, roomName } = connectionInfo;

      // 2. Initialize LiveKit Room object
      const room = new Room();
      roomRef.current = room;

      // 3. Register Event Listeners
      room.on(RoomEvent.Connected, () => {
        setStatus('connected');
      });

      room.on(RoomEvent.Disconnected, () => {
        handleDisconnect();
      });

      // Handle speech state changes (active speakers)
      room.on(RoomEvent.ActiveSpeakersChanged, (speakers) => {
        if (room.state !== 'connected') return;

        // Check if any speaker is remote (the bot agent)
        const isBotSpeaking = speakers.some((s) => !s.isLocal);
        // Check if local speaker is active
        const isMeSpeaking = speakers.some((s) => s.isLocal);

        if (isBotSpeaking) {
          setStatus('speaking');
        } else if (isMeSpeaking) {
          setStatus('listening');
        } else {
          setStatus('connected');
        }
      });

      // Listen for text transcripts sent over the LiveKit Data Channel
      room.on(RoomEvent.DataReceived, (payload: Uint8Array, participant?: Participant) => {
        try {
          // Decode UTF-8 string safely (critical for Telugu unicode)
          const str = decodeUTF8(payload);

          // Parse JSON transcript
          const data = JSON.parse(str);
          if (data && data.text) {
            const sender = data.type === 'user_transcript' ? 'user' : 'bot';

            setMessages((prev) => {
              // Deduplicate or append message
              const newMsg: ChatMessage = {
                id: Math.random().toString(),
                sender,
                text: data.text,
              };
              return [...prev, newMsg];
            });

            // Auto-scroll transcript container
            setTimeout(() => {
              scrollViewRef.current?.scrollToEnd({ animated: true });
            }, 100);
          }
        } catch (e) {
          console.error('Failed to parse incoming data message:', e);
        }
      });

      // 4. Start the native audio session (essential for WebRTC audio routing on mobile)
      await AudioSession.startAudioSession();

      // 5. Connect to Room
      await room.connect(url, token);

      // 5. Publish local microphone track
      await room.localParticipant.setMicrophoneEnabled(true);

    } catch (err: any) {
      console.error('Connection failed:', err);
      setError(err?.message || 'Failed to connect. Make sure backend is running.');
      setStatus('disconnected');
    }
  };

  const disconnectSession = async () => {
    if (roomRef.current) {
      await roomRef.current.disconnect();
    }
    handleDisconnect();
  };

  const handleDisconnect = () => {
    roomRef.current = null;
    setStatus('disconnected');
    AudioSession.stopAudioSession().catch((e) => {
      console.warn('Failed to stop audio session:', e);
    });
  };

  // Clean up on component unmount
  useEffect(() => {
    return () => {
      if (roomRef.current) {
        roomRef.current.disconnect();
      }
    };
  }, []);

  // Format statuses into user friendly English texts
  const getStatusText = () => {
    switch (status) {
      case 'disconnected':
        return 'Disconnected';
      case 'connecting':
        return 'Connecting...';
      case 'connected':
        return 'Ready — start speaking';
      case 'listening':
        return 'Listening...';
      case 'speaking':
        return 'Navya is speaking...';
      default:
        return '';
    }
  };

  return (
    <SafeAreaView style={styles.container}>
      <StatusBar barStyle="light-content" backgroundColor="#0B0C10" />

      {/* Header Bar */}
      <View style={styles.header}>
        <View>
          <Text style={styles.headerTitle}>Navya</Text>
          <Text style={styles.headerSubtitle}>Telugu AI Voice Assistant</Text>
        </View>
        <TouchableOpacity
          style={styles.settingsButton}
          onPress={() => setShowSettings(!showSettings)}
        >
          <Text style={styles.settingsIcon}>⚙️</Text>
        </TouchableOpacity>
      </View>

      {/* Collapsible Settings Drawer */}
      {showSettings && (
        <View style={styles.settingsPanel}>
          <Text style={styles.settingsLabel}>Server URL (FastAPI Backend):</Text>
          <TextInput
            style={styles.settingsInput}
            value={serverUrl}
            onChangeText={setServerUrl}
            placeholder="http://192.168.1.x:8000"
            placeholderTextColor="#888"
            autoCapitalize="none"
            autoCorrect={false}
          />
          <Text style={styles.settingsHint}>
            * Connect via your computer's local IP over WiFi. (e.g. http://192.168.1.100:8000)
          </Text>
        </View>
      )}

      {/* Options/Persona Selector */}
      {status === 'disconnected' && (
        <View style={styles.personaContainer}>
          <Text style={styles.personaLabel}>Select Agent Role:</Text>
          <View style={styles.personaButtonsContainer}>
            <TouchableOpacity
              style={[styles.personaButton, persona === 'prank' && styles.personaButtonActive]}
              onPress={() => setPersona('prank')}
            >
              <Text style={[styles.personaButtonText, persona === 'prank' && styles.personaButtonTextActive]}>
                😜 Prank
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.personaButton, persona === 'support' && styles.personaButtonActive]}
              onPress={() => setPersona('support')}
            >
              <Text style={[styles.personaButtonText, persona === 'support' && styles.personaButtonTextActive]}>
                🛠️ Support
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.personaButton, persona === 'real_estate' && styles.personaButtonActive]}
              onPress={() => setPersona('real_estate')}
            >
              <Text style={[styles.personaButtonText, persona === 'real_estate' && styles.personaButtonTextActive]}>
                🏢 Real Estate
              </Text>
            </TouchableOpacity>
          </View>
        </View>
      )}

      {/* Interactive Breathing Visualizer */}
      <View style={styles.visualizerContainer}>
        {/* Wrapper to align the absolute glow ring and main orb perfectly */}
        <View style={styles.orbWrapper}>
          {/* Animated Glow Rings */}
          <Animated.View style={[styles.glowRing, animatedGlowStyle]} />

          {/* Main Central Orb */}
          <Animated.View style={[styles.orb, animatedOrbStyle]}>
            <Text style={styles.orbEmoji}>🎙️</Text>
          </Animated.View>
        </View>

        <Text style={styles.statusText}>{getStatusText()}</Text>
        {error && <Text style={styles.errorText}>{error}</Text>}
      </View>

      {/* Conversation Log Bubble Container */}
      <View style={styles.logContainer}>
        <Text style={styles.logHeader}>Conversation</Text>
        <ScrollView
          ref={scrollViewRef}
          style={styles.logScrollView}
          contentContainerStyle={styles.logContent}
        >
          {messages.length === 0 ? (
            <Text style={styles.placeholderLogText}>
              Your conversation will appear here. Start speaking...
            </Text>
          ) : (
            messages.map((msg) => (
              <View
                key={msg.id}
                style={[
                  styles.messageRow,
                  msg.sender === 'user' ? styles.userRow : styles.botRow,
                ]}
              >
                <View
                  style={[
                    styles.messageBubble,
                    msg.sender === 'user' ? styles.userBubble : styles.botBubble,
                  ]}
                >
                  <Text style={styles.messageText}>{msg.text}</Text>
                </View>
              </View>
            ))
          )}
        </ScrollView>
      </View>

      {/* Connection Controller gradient button */}
      <View style={styles.footer}>
        {status === 'disconnected' ? (
          <TouchableOpacity style={[styles.button, styles.connectButton]} onPress={connectSession}>
            <Text style={styles.buttonText}>Connect</Text>
          </TouchableOpacity>
        ) : (
          <TouchableOpacity style={[styles.button, styles.disconnectButton]} onPress={disconnectSession}>
            <Text style={styles.buttonText}>Disconnect</Text>
          </TouchableOpacity>
        )}
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#0B0C10',
  },
  header: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 20,
    paddingVertical: 15,
    paddingTop: Platform.OS === 'android' ? (StatusBar.currentHeight ?? 0) + 12 : 15,
    borderBottomWidth: 1,
    borderBottomColor: '#1f2833',
  },
  headerTitle: {
    fontSize: 26,
    fontWeight: 'bold',
    color: '#00F2FE',
    fontFamily: Platform.OS === 'ios' ? 'System' : 'sans-serif-medium',
  },
  headerSubtitle: {
    fontSize: 12,
    color: '#8892B0',
    marginTop: 2,
  },
  settingsButton: {
    padding: 8,
  },
  settingsIcon: {
    fontSize: 22,
  },
  settingsPanel: {
    backgroundColor: 'rgba(255, 255, 255, 0.05)',
    padding: 15,
    marginHorizontal: 15,
    marginTop: 10,
    borderRadius: 8,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.1)',
  },
  settingsLabel: {
    color: '#fff',
    fontSize: 14,
    marginBottom: 8,
  },
  settingsInput: {
    backgroundColor: '#1B1C22',
    color: '#fff',
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: '#45F3FF',
    fontSize: 14,
  },
  settingsHint: {
    color: '#888',
    fontSize: 11,
    marginTop: 6,
    lineHeight: 15,
  },
  visualizerContainer: {
    flex: 1.2,
    justifyContent: 'center',
    alignItems: 'center',
    paddingVertical: 20,
  },
  orbWrapper: {
    width: 180,
    height: 180,
    justifyContent: 'center',
    alignItems: 'center',
    position: 'relative',
  },
  orb: {
    width: 110,
    height: 110,
    borderRadius: 55,
    justifyContent: 'center',
    alignItems: 'center',
    zIndex: 2,
    elevation: 8,
    shadowColor: '#4FACFE',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.4,
    shadowRadius: 8,
  },
  orbEmoji: {
    fontSize: 34,
  },
  glowRing: {
    position: 'absolute',
    width: 110,
    height: 110,
    borderRadius: 55,
    borderWidth: 3,
    zIndex: 1,
  },
  statusText: {
    color: '#fff',
    fontSize: 16,
    fontWeight: '600',
    marginTop: 35,
    textAlign: 'center',
    letterSpacing: 0.5,
  },
  errorText: {
    color: '#FF4D4D',
    fontSize: 13,
    marginTop: 10,
    textAlign: 'center',
    paddingHorizontal: 30,
  },
  logContainer: {
    flex: 1,
    backgroundColor: 'rgba(255, 255, 255, 0.03)',
    marginHorizontal: 15,
    marginBottom: 15,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.06)',
    overflow: 'hidden',
  },
  logHeader: {
    color: '#8892B0',
    fontSize: 12,
    fontWeight: 'bold',
    textTransform: 'uppercase',
    paddingHorizontal: 15,
    paddingVertical: 10,
    backgroundColor: 'rgba(255, 255, 255, 0.02)',
    borderBottomWidth: 1,
    borderBottomColor: 'rgba(255, 255, 255, 0.05)',
  },
  logScrollView: {
    flex: 1,
  },
  logContent: {
    padding: 15,
    paddingBottom: 25,
  },
  placeholderLogText: {
    color: '#555',
    fontSize: 13,
    textAlign: 'center',
    marginTop: 40,
    lineHeight: 20,
    paddingHorizontal: 20,
  },
  messageRow: {
    marginVertical: 6,
    flexDirection: 'row',
    width: '100%',
  },
  userRow: {
    justifyContent: 'flex-end',
  },
  botRow: {
    justifyContent: 'flex-start',
  },
  messageBubble: {
    maxWidth: '80%',
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 16,
  },
  userBubble: {
    backgroundColor: '#1E1F26',
    borderTopRightRadius: 2,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.08)',
  },
  botBubble: {
    backgroundColor: 'rgba(79, 172, 254, 0.1)',
    borderTopLeftRadius: 2,
    borderWidth: 1,
    borderColor: 'rgba(79, 172, 254, 0.2)',
  },
  messageText: {
    color: '#E6F4FE',
    fontSize: 14,
    lineHeight: 20,
  },
  footer: {
    paddingHorizontal: 20,
    paddingBottom: Platform.OS === 'ios' ? 25 : 20,
  },
  button: {
    width: '100%',
    height: 52,
    borderRadius: 26,
    justifyContent: 'center',
    alignItems: 'center',
    shadowColor: '#000',
    shadowOffset: { width: 0, height: 4 },
    shadowOpacity: 0.3,
    shadowRadius: 5,
    elevation: 5,
  },
  connectButton: {
    backgroundColor: '#00F2FE', // Electric Cyan
  },
  disconnectButton: {
    backgroundColor: '#FF416C', // Reddish Pink
  },
  buttonText: {
    color: '#0B0C10',
    fontSize: 17,
    fontWeight: 'bold',
    letterSpacing: 0.5,
  },
  personaContainer: {
    paddingHorizontal: 20,
    marginVertical: 15,
  },
  personaLabel: {
    color: '#8892B0',
    fontSize: 13,
    fontWeight: '600',
    textTransform: 'uppercase',
    marginBottom: 10,
    letterSpacing: 0.5,
  },
  personaButtonsContainer: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    backgroundColor: '#1E1F26',
    borderRadius: 12,
    padding: 4,
    borderWidth: 1,
    borderColor: 'rgba(255, 255, 255, 0.08)',
  },
  personaButton: {
    flex: 1,
    paddingVertical: 10,
    borderRadius: 8,
    alignItems: 'center',
    justifyContent: 'center',
  },
  personaButtonActive: {
    backgroundColor: '#00F2FE',
    shadowColor: '#00F2FE',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.2,
    shadowRadius: 4,
    elevation: 3,
  },
  personaButtonText: {
    color: '#8892B0',
    fontSize: 12,
    fontWeight: '600',
  },
  personaButtonTextActive: {
    color: '#0B0C10',
    fontWeight: 'bold',
  },
});
