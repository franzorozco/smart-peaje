import Ionicons from '@expo/vector-icons/Ionicons';
import { Image } from 'expo-image';
import * as ImagePicker from 'expo-image-picker';
import { useCallback, useRef, useState } from 'react';
import {
  ActivityIndicator,
  FlatList,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { EstadoBadge } from '@/components/EstadoBadge';
import { Fonts, Palette } from '@/constants/theme';
import { enviarConsultaImagen, enviarConsultaTexto, toApiError } from '@/lib/api';
import type { AgenteChatResponse, ArchivoCaptura } from '@/lib/types';

interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  text?: string;
  imageUri?: string;
  response?: AgenteChatResponse;
  error?: string;
}

const INITIAL_MESSAGES: ChatMessage[] = [
  {
    id: 'welcome',
    role: 'assistant',
    response: {
      respuesta:
        'Consulta cualquier placa escribiéndola (por ejemplo 1234ABC) o adjunta una fotografía desde Galería o Cámara.',
      tool: 'aclaracion',
      estado: null,
      datos: null,
      sugerencias: [],
      requiere: null,
    },
  },
];

function createMessageId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
}

const CATEGORIAS_LABELS: Record<string, string> = {
  moto: 'Moto',
  auto: 'Auto',
  minibus: 'Minibús',
  camion: 'Camión',
  bus: 'Bus',
};

function formatCategoria(cat: string): string {
  const key = (cat || '').trim().toLowerCase();
  return CATEGORIAS_LABELS[key] ?? cat;
}

function formatFecha(iso: string): string {
  try {
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) {
      return iso;
    }
    return date.toLocaleString('es-BO', {
      dateStyle: 'short',
      timeStyle: 'short',
    });
  } catch {
    return iso;
  }
}

function assetToArchivo(asset: ImagePicker.ImagePickerAsset): ArchivoCaptura {
  const uriLower = asset.uri.toLowerCase();
  const isPng = asset.mimeType === 'image/png' || uriLower.endsWith('.png');
  return {
    uri: asset.uri,
    name: asset.fileName || (isPng ? 'placa.png' : 'placa.jpg'),
    type: asset.mimeType || (isPng ? 'image/png' : 'image/jpeg'),
  };
}

export default function ConsultaScreen() {
  const [messages, setMessages] = useState<ChatMessage[]>(INITIAL_MESSAGES);
  const [inputText, setInputText] = useState('');
  const [sending, setSending] = useState(false);
  const listRef = useRef<FlatList<ChatMessage> | null>(null);

  const scrollToBottom = useCallback(() => {
    setTimeout(() => {
      listRef.current?.scrollToEnd({ animated: true });
    }, 80);
  }, []);

  const appendMessage = useCallback(
    (msg: ChatMessage) => {
      setMessages((prev) => [...prev, msg]);
      scrollToBottom();
    },
    [scrollToBottom]
  );

  const handleSendText = useCallback(
    async (textOverride?: string) => {
      const text = (textOverride ?? inputText).trim();
      if (!text || sending) {
        return;
      }

      if (!textOverride) {
        setInputText('');
      }

      appendMessage({
        id: createMessageId(),
        role: 'user',
        text,
      });

      setSending(true);
      try {
        const res = await enviarConsultaTexto(text);
        appendMessage({
          id: createMessageId(),
          role: 'assistant',
          response: res,
        });
      } catch (error) {
        const apiErr = toApiError(error, 'No se pudo realizar la consulta.');
        appendMessage({
          id: createMessageId(),
          role: 'assistant',
          error: apiErr.message,
        });
      } finally {
        setSending(false);
      }
    },
    [appendMessage, inputText, sending]
  );

  const handleSendAsset = useCallback(
    async (asset: ImagePicker.ImagePickerAsset) => {
      if (sending) {
        return;
      }

      const optionalText = inputText.trim();
      if (optionalText) {
        setInputText('');
      }

      appendMessage({
        id: createMessageId(),
        role: 'user',
        text: optionalText || 'Consulta por imagen de placa',
        imageUri: asset.uri,
      });

      setSending(true);
      try {
        const res = await enviarConsultaImagen(assetToArchivo(asset), optionalText || undefined);
        appendMessage({
          id: createMessageId(),
          role: 'assistant',
          response: res,
        });
      } catch (error) {
        const apiErr = toApiError(error, 'No se pudo analizar la imagen.');
        appendMessage({
          id: createMessageId(),
          role: 'assistant',
          error: apiErr.message,
        });
      } finally {
        setSending(false);
      }
    },
    [appendMessage, inputText, sending]
  );

  const handlePickGallery = async () => {
    if (sending) {
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images'],
      quality: 0.85,
    });

    if (!result.canceled && result.assets[0]) {
      await handleSendAsset(result.assets[0]);
    }
  };

  const handlePickCamera = async () => {
    if (sending) {
      return;
    }

    const perm = await ImagePicker.requestCameraPermissionsAsync();
    if (!perm.granted) {
      appendMessage({
        id: createMessageId(),
        role: 'assistant',
        error: 'Se necesita permiso de cámara para fotografiar la placa.',
      });
      return;
    }

    const result = await ImagePicker.launchCameraAsync({
      mediaTypes: ['images'],
      quality: 0.85,
    });

    if (!result.canceled && result.assets[0]) {
      await handleSendAsset(result.assets[0]);
    }
  };

  const renderMessage = ({ item }: { item: ChatMessage }) => {
    if (item.role === 'user') {
      return (
        <View style={styles.userBubbleWrap}>
          <View style={styles.userBubble}>
            {item.imageUri ? (
              <Image source={{ uri: item.imageUri }} style={styles.userImage} contentFit="cover" />
            ) : null}
            {item.text ? <Text style={styles.userText}>{item.text}</Text> : null}
          </View>
        </View>
      );
    }

    if (item.error) {
      return (
        <View style={styles.assistantBubbleWrap}>
          <View style={[styles.assistantBubble, styles.errorBubble]}>
            <View style={styles.errorRow}>
              <Ionicons name="alert-circle" size={16} color={Palette.dangerText} />
              <Text style={styles.errorText}>{item.error}</Text>
            </View>
          </View>
        </View>
      );
    }

    const res = item.response;
    if (!res) {
      return null;
    }

    const datos = res.datos;
    const ultimoPaso = datos?.ultimo_paso;
    const historialPasos = !ultimoPaso && datos?.pasos?.length ? datos.pasos.slice(0, 5) : null;
    const sugerencias = res.sugerencias?.length ? res.sugerencias : (datos?.sugerencias ?? []);

    return (
      <View style={styles.assistantBubbleWrap}>
        <View style={styles.assistantBubble}>
          {res.estado ? <EstadoBadge estado={res.estado} /> : null}

          <Text style={styles.assistantText}>{res.respuesta}</Text>

          {datos?.lectura ? (
            <View style={styles.infoBox}>
              <Text style={styles.infoTitle}>Lectura OCR</Text>
              <Text style={styles.infoLine}>
                Placa: <Text style={styles.monoStrong}>{datos.lectura.placa}</Text> · Confianza:{' '}
                {Math.round(
                  datos.lectura.confianza <= 1
                    ? datos.lectura.confianza * 100
                    : datos.lectura.confianza
                )}
                %
              </Text>
            </View>
          ) : null}

          {datos?.vehiculo ? (
            <View style={styles.infoBox}>
              <Text style={styles.infoTitle}>Vehículo</Text>
              <Text style={styles.infoLine}>
                {datos.vehiculo.placa} · {formatCategoria(datos.vehiculo.categoria)} · {datos.vehiculo.ejes} ejes ·{' '}
                {datos.vehiculo.activo ? 'Activo' : 'Inactivo'}
              </Text>
            </View>
          ) : null}

          {ultimoPaso ? (
            <View style={styles.ultimoPasoCard}>
              <View style={styles.ultimoPasoHeader}>
                <Text style={styles.infoTitle}>Último paso</Text>
                <EstadoBadge estado={String(ultimoPaso.estado_pago)} />
              </View>
              <Text style={styles.infoLine}>Caseta: {ultimoPaso.caseta}</Text>
              <Text style={styles.infoLine}>
                Categoría: {formatCategoria(ultimoPaso.categoria)} · Tarifa: Bs {ultimoPaso.monto}
              </Text>
              <Text style={styles.infoMuted}>Fecha: {formatFecha(ultimoPaso.fecha)}</Text>
            </View>
          ) : null}

          {historialPasos ? (
            <View style={styles.ultimoPasoCard}>
              <Text style={styles.infoTitle}>Pasos recientes ({datos?.total ?? historialPasos.length})</Text>
              {historialPasos.map((p) => (
                <View key={p.id} style={styles.historyRow}>
                  <View style={styles.historyLeft}>
                    <Text style={styles.infoLine}>{p.caseta_nombre}</Text>
                    <Text style={styles.infoMuted}>
                      {formatFecha(p.created_at)} · Bs {p.monto}
                    </Text>
                  </View>
                  <EstadoBadge estado={p.estado} />
                </View>
              ))}
            </View>
          ) : null}

          {sugerencias.length > 0 ? (
            <View style={styles.suggestionsWrap}>
              <Text style={styles.suggestionsLabel}>Sugerencias:</Text>
              <View style={styles.suggestionsRow}>
                {sugerencias.map((placa) => (
                  <Pressable
                    key={placa}
                    style={({ pressed }) => [styles.suggestionChip, pressed && styles.pressed]}
                    disabled={sending}
                    onPress={() => handleSendText(placa)}>
                    <Text style={styles.suggestionText}>{placa}</Text>
                  </Pressable>
                ))}
              </View>
            </View>
          ) : null}
        </View>
      </View>
    );
  };

  return (
    <KeyboardAvoidingView
      style={styles.screen}
      behavior={Platform.OS === 'ios' ? 'padding' : 'height'}
      keyboardVerticalOffset={Platform.OS === 'ios' ? 90 : 70}>
      <FlatList
        ref={listRef}
        data={messages}
        keyExtractor={(item) => item.id}
        renderItem={renderMessage}
        contentContainerStyle={styles.listContent}
        onContentSizeChange={scrollToBottom}
      />

      {sending ? (
        <View style={styles.typingRow}>
          <ActivityIndicator size="small" color={Palette.primary} />
          <Text style={styles.typingText}>Consultando agente...</Text>
        </View>
      ) : null}

      <View style={styles.composer}>
        <View style={styles.mediaActions}>
          <Pressable
            style={({ pressed }) => [
              styles.mediaButton,
              sending && styles.disabled,
              pressed && styles.pressed,
            ]}
            disabled={sending}
            onPress={handlePickGallery}>
            <Ionicons name="images-outline" size={18} color={Palette.primary} />
            <Text style={styles.mediaButtonText}>Galería</Text>
          </Pressable>

          <Pressable
            style={({ pressed }) => [
              styles.mediaButton,
              sending && styles.disabled,
              pressed && styles.pressed,
            ]}
            disabled={sending}
            onPress={handlePickCamera}>
            <Ionicons name="camera-outline" size={18} color={Palette.primary} />
            <Text style={styles.mediaButtonText}>Cámara</Text>
          </Pressable>
        </View>

        <View style={styles.inputRow}>
          <TextInput
            style={styles.input}
            value={inputText}
            onChangeText={setInputText}
            placeholder="Placa o pregunta (ej. 1234ABC)"
            placeholderTextColor={Palette.textMuted}
            autoCapitalize="characters"
            returnKeyType="send"
            editable={!sending}
            onSubmitEditing={() => handleSendText()}
          />
          <Pressable
            style={({ pressed }) => [
              styles.sendButton,
              (!inputText.trim() || sending) && styles.disabled,
              pressed && styles.pressed,
            ]}
            disabled={!inputText.trim() || sending}
            onPress={() => handleSendText()}>
            <Ionicons name="send" size={18} color="#FFFFFF" />
          </Pressable>
        </View>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: Palette.background,
  },
  listContent: {
    padding: 16,
    gap: 12,
  },
  userBubbleWrap: {
    alignItems: 'flex-end',
  },
  userBubble: {
    maxWidth: '82%',
    backgroundColor: Palette.primary,
    borderRadius: 16,
    borderBottomRightRadius: 4,
    padding: 12,
    gap: 8,
  },
  userImage: {
    width: 180,
    height: 120,
    borderRadius: 10,
  },
  userText: {
    color: '#FFFFFF',
    fontSize: 15,
    lineHeight: 20,
  },
  assistantBubbleWrap: {
    alignItems: 'flex-start',
  },
  assistantBubble: {
    maxWidth: '90%',
    backgroundColor: Palette.surface,
    borderWidth: 1,
    borderColor: Palette.border,
    borderRadius: 16,
    borderBottomLeftRadius: 4,
    padding: 14,
    gap: 10,
  },
  errorBubble: {
    backgroundColor: Palette.dangerBg,
    borderColor: Palette.dangerBg,
  },
  errorRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  errorText: {
    flex: 1,
    color: Palette.dangerText,
    fontSize: 14,
    lineHeight: 19,
  },
  assistantText: {
    fontSize: 15,
    color: Palette.text,
    lineHeight: 21,
  },
  infoBox: {
    backgroundColor: Palette.surfaceMuted,
    borderRadius: 10,
    padding: 10,
    gap: 3,
  },
  ultimoPasoCard: {
    backgroundColor: Palette.surfaceMuted,
    borderRadius: 12,
    padding: 12,
    gap: 6,
  },
  ultimoPasoHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    gap: 8,
  },
  infoTitle: {
    fontSize: 12,
    fontWeight: '700',
    color: Palette.textMuted,
    textTransform: 'uppercase',
  },
  infoLine: {
    fontSize: 14,
    color: Palette.text,
    fontWeight: '500',
  },
  infoMuted: {
    fontSize: 12,
    color: Palette.textSecondary,
  },
  monoStrong: {
    fontFamily: Fonts?.mono,
    fontWeight: '700',
  },
  historyRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    borderTopWidth: 1,
    borderTopColor: Palette.border,
    paddingTop: 6,
    gap: 8,
  },
  historyLeft: {
    flex: 1,
  },
  suggestionsWrap: {
    gap: 6,
  },
  suggestionsLabel: {
    fontSize: 12,
    color: Palette.textMuted,
    fontWeight: '600',
  },
  suggestionsRow: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 8,
  },
  suggestionChip: {
    backgroundColor: Palette.primaryLight,
    borderWidth: 1,
    borderColor: Palette.primary,
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  suggestionText: {
    color: Palette.primary,
    fontSize: 13,
    fontWeight: '700',
    fontFamily: Fonts?.mono,
  },
  typingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingHorizontal: 16,
    paddingVertical: 6,
  },
  typingText: {
    fontSize: 13,
    color: Palette.textSecondary,
  },
  composer: {
    backgroundColor: Palette.surface,
    borderTopWidth: 1,
    borderTopColor: Palette.border,
    paddingHorizontal: 12,
    paddingTop: 10,
    paddingBottom: 12,
    gap: 8,
  },
  mediaActions: {
    flexDirection: 'row',
    gap: 8,
  },
  mediaButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: Palette.primaryLight,
    paddingHorizontal: 12,
    paddingVertical: 8,
    borderRadius: 10,
  },
  mediaButtonText: {
    color: Palette.primary,
    fontSize: 13,
    fontWeight: '700',
  },
  inputRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  input: {
    flex: 1,
    backgroundColor: Palette.surfaceMuted,
    borderRadius: 12,
    paddingHorizontal: 14,
    paddingVertical: 11,
    fontSize: 15,
    color: Palette.text,
  },
  sendButton: {
    backgroundColor: Palette.primary,
    width: 44,
    height: 44,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  disabled: {
    opacity: 0.45,
  },
  pressed: {
    opacity: 0.8,
  },
});
