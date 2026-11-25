import Ionicons from '@expo/vector-icons/Ionicons';
import { CameraView, useCameraPermissions } from 'expo-camera';
import * as Crypto from 'expo-crypto';
import * as ImagePicker from 'expo-image-picker';
import { useIsFocused } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Linking,
  Modal,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { ResultadoPaso } from '@/components/ResultadoPaso';
import { Palette } from '@/constants/theme';
import { ApiError, enviarCapturaCaseta, toApiError } from '@/lib/api';
import type { ArchivoCaptura, PasoFrameResponse } from '@/lib/types';
import { useCasetas } from '@/lib/use-casetas';

const CLIP_DURATION_SECONDS = 6;

interface PendingCapture {
  capturaId: string;
  file: ArchivoCaptura;
}

function buildVideoFile(uri: string): ArchivoCaptura {
  const isMov = uri.toLowerCase().endsWith('.mov');
  return {
    uri,
    name: isMov ? 'captura.mov' : 'captura.mp4',
    type: isMov ? 'video/quicktime' : 'video/mp4',
  };
}

function buildPhotoFile(uri: string): ArchivoCaptura {
  const isPng = uri.toLowerCase().endsWith('.png');
  return {
    uri,
    name: isPng ? 'captura.png' : 'captura.jpg',
    type: isPng ? 'image/png' : 'image/jpeg',
  };
}

export default function CasetaScreen() {
  const isFocused = useIsFocused();
  const [permission, requestPermission] = useCameraPermissions();
  const {
    casetas,
    selectedCasetaId,
    selectedCaseta,
    selectCaseta,
    loading: loadingCasetas,
    error: casetasError,
    reload: reloadCasetas,
  } = useCasetas();

  const cameraRef = useRef<CameraView | null>(null);
  const readyResolverRef = useRef<(() => void) | null>(null);
  const countdownTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const [cameraMode, setCameraMode] = useState<'video' | 'picture'>('video');
  const [cameraMountError, setCameraMountError] = useState<string | null>(null);
  const [pickerVisible, setPickerVisible] = useState(false);

  const [isRecording, setIsRecording] = useState(false);
  const [isCapturingPhoto, setIsCapturingPhoto] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [countdown, setCountdown] = useState(0);

  const [pendingCapture, setPendingCapture] = useState<PendingCapture | null>(null);
  const [resultado, setResultado] = useState<PasoFrameResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [errorRequiresNew, setErrorRequiresNew] = useState(false);

  const clearCountdownTimer = useCallback(() => {
    if (countdownTimerRef.current) {
      clearInterval(countdownTimerRef.current);
      countdownTimerRef.current = null;
    }
  }, []);

  useEffect(() => {
    return () => {
      clearCountdownTimer();
      readyResolverRef.current = null;
    };
  }, [clearCountdownTimer]);

  const handleCameraReady = useCallback(() => {
    setCameraMountError(null);
    if (readyResolverRef.current) {
      const resolve = readyResolverRef.current;
      readyResolverRef.current = null;
      setTimeout(resolve, 120);
    }
  }, []);

  const uploadCapture = useCallback(
    async (capture: PendingCapture) => {
      if (!selectedCasetaId) {
        setErrorMsg('Selecciona una caseta antes de enviar la captura.');
        setErrorRequiresNew(false);
        return;
      }

      setPendingCapture(capture);
      setIsUploading(true);
      setErrorMsg(null);
      setErrorRequiresNew(false);

      try {
        const res = await enviarCapturaCaseta({
          file: capture.file,
          capturaId: capture.capturaId,
          casetaId: selectedCasetaId,
        });
        setResultado(res);
        setErrorMsg(null);
        setErrorRequiresNew(false);
      } catch (error) {
        const apiErr = error instanceof ApiError ? error : toApiError(error);
        if (apiErr.status === 422) {
          setErrorMsg(`Se requiere nueva captura: ${apiErr.message}`);
          setErrorRequiresNew(true);
        } else if (apiErr.status === 503) {
          setErrorMsg(apiErr.message || 'Servicio de inferencia no disponible');
          setErrorRequiresNew(false);
        } else {
          setErrorMsg(apiErr.message);
          setErrorRequiresNew(false);
        }
      } finally {
        setIsUploading(false);
      }
    },
    [selectedCasetaId]
  );

  const handleRecordClip = async () => {
    if (!cameraRef.current || !selectedCasetaId || isRecording || isCapturingPhoto || isUploading) {
      return;
    }

    setResultado(null);
    setErrorMsg(null);
    setErrorRequiresNew(false);
    setPendingCapture(null);
    setIsRecording(true);
    setCountdown(CLIP_DURATION_SECONDS);

    clearCountdownTimer();
    countdownTimerRef.current = setInterval(() => {
      setCountdown((prev) => (prev > 1 ? prev - 1 : 1));
    }, 1000);

    try {
      const video = await cameraRef.current.recordAsync({
        maxDuration: CLIP_DURATION_SECONDS,
      });

      clearCountdownTimer();
      setIsRecording(false);
      setCountdown(0);

      if (!video?.uri) {
        setErrorMsg('No se obtuvo el archivo de video.');
        return;
      }

      const capture: PendingCapture = {
        capturaId: Crypto.randomUUID(),
        file: buildVideoFile(video.uri),
      };
      await uploadCapture(capture);
    } catch (error) {
      clearCountdownTimer();
      setIsRecording(false);
      setCountdown(0);
      setErrorMsg(
        error instanceof Error ? error.message : 'No se pudo completar la grabación del clip.'
      );
    }
  };

  const waitForPictureMode = useCallback(() => {
    return new Promise<void>((resolve) => {
      const fallbackMs = Platform.OS === 'android' ? 950 : 450;
      const timer = setTimeout(() => {
        readyResolverRef.current = null;
        resolve();
      }, fallbackMs);

      readyResolverRef.current = () => {
        clearTimeout(timer);
        resolve();
      };
    });
  }, []);

  const handleTakePhoto = async () => {
    if (!cameraRef.current || !selectedCasetaId || isRecording || isCapturingPhoto || isUploading) {
      return;
    }

    setResultado(null);
    setErrorMsg(null);
    setErrorRequiresNew(false);
    setPendingCapture(null);
    setIsCapturingPhoto(true);

    try {
      setCameraMode('picture');
      await waitForPictureMode();

      if (!cameraRef.current) {
        throw new Error('La cámara no está disponible.');
      }

      let photo;
      try {
        photo = await cameraRef.current.takePictureAsync({ quality: 0.85 });
      } catch {
        await new Promise((r) => setTimeout(r, 280));
        photo = await cameraRef.current?.takePictureAsync({ quality: 0.85 });
      }

      setCameraMode('video');

      if (!photo?.uri) {
        setErrorMsg('No se obtuvo la fotografía de respaldo.');
        return;
      }

      const capture: PendingCapture = {
        capturaId: Crypto.randomUUID(),
        file: buildPhotoFile(photo.uri),
      };
      await uploadCapture(capture);
    } catch (error) {
      setErrorMsg(error instanceof Error ? error.message : 'No se pudo tomar la fotografía.');
    } finally {
      readyResolverRef.current = null;
      setCameraMode('video');
      setIsCapturingPhoto(false);
    }
  };

  const handlePickFromGallery = async () => {
    if (!selectedCasetaId || isRecording || isCapturingPhoto || isUploading) {
      return;
    }

    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['images', 'videos'],
      quality: 0.85,
    });

    if (result.canceled || !result.assets[0]) {
      return;
    }

    const asset = result.assets[0];
    setResultado(null);
    setErrorMsg(null);
    setErrorRequiresNew(false);
    setPendingCapture(null);

    const isVid = asset.type === 'video' || /\.(mp4|mov)$/i.test(asset.uri);
    const capture: PendingCapture = {
      capturaId: Crypto.randomUUID(),
      file: isVid ? buildVideoFile(asset.uri) : buildPhotoFile(asset.uri),
    };
    await uploadCapture(capture);
  };

  const handleRetryUpload = async () => {
    if (!pendingCapture || isUploading || isRecording || isCapturingPhoto) {
      return;
    }
    await uploadCapture(pendingCapture);
  };

  const handleNewCapture = () => {
    setPendingCapture(null);
    setResultado(null);
    setErrorMsg(null);
    setErrorRequiresNew(false);
  };

  if (!permission) {
    return (
      <View style={styles.centered}>
        <ActivityIndicator size="large" color={Palette.primary} />
        <Text style={styles.mutedText}>Verificando permiso de cámara...</Text>
      </View>
    );
  }

  if (!permission.granted) {
    return (
      <View style={styles.centered}>
        <View style={styles.permissionCard}>
          <Ionicons name="camera-outline" size={44} color={Palette.primary} />
          <Text style={styles.permissionTitle}>Permiso de cámara requerido</Text>
          <Text style={styles.permissionBody}>
            La cámara se usa para capturar clips o fotografías de los vehículos que pasan por la
            caseta.
          </Text>
          <Pressable style={styles.primaryButton} onPress={requestPermission}>
            <Text style={styles.primaryButtonText}>Conceder permiso</Text>
          </Pressable>
          {!permission.canAskAgain ? (
            <Pressable style={styles.secondaryButton} onPress={() => Linking.openSettings()}>
              <Text style={styles.secondaryButtonText}>Abrir ajustes del sistema</Text>
            </Pressable>
          ) : null}
        </View>
      </View>
    );
  }

  const controlsDisabled = isRecording || isCapturingPhoto || isUploading || !selectedCasetaId;

  return (
    <ScrollView style={styles.screen} contentContainerStyle={styles.content}>
      {/* Selector de Caseta */}
      <Pressable
        style={styles.casetaBar}
        disabled={isRecording || isUploading}
        onPress={() => setPickerVisible(true)}>
        <View style={styles.casetaInfo}>
          <Ionicons name="business-outline" size={20} color={Palette.primary} />
          <View style={styles.casetaTextWrap}>
            <Text style={styles.casetaLabel}>Caseta activa</Text>
            {loadingCasetas ? (
              <Text style={styles.casetaName}>Cargando casetas...</Text>
            ) : selectedCaseta ? (
              <Text style={styles.casetaName} numberOfLines={1}>
                {selectedCaseta.nombre} · {selectedCaseta.ubicacion}
              </Text>
            ) : (
              <Text style={styles.casetaError}>
                {casetasError ?? 'Sin casetas disponibles'}
              </Text>
            )}
          </View>
        </View>
        <View style={styles.casetaRight}>
          <Text style={styles.casetaAction}>{casetas.length > 0 ? 'Cambiar' : 'Reintentar'}</Text>
          <Ionicons name="chevron-down" size={18} color={Palette.primary} />
        </View>
      </Pressable>

      {/* Visor de Cámara */}
      <View style={styles.cameraFrame}>
        {isFocused ? (
          <CameraView
            ref={cameraRef}
            style={styles.camera}
            mode={cameraMode}
            facing="back"
            mute
            videoQuality="720p"
            onCameraReady={handleCameraReady}
            onMountError={(event) => setCameraMountError(event.message)}
          />
        ) : (
          <View style={styles.cameraPaused}>
            <Ionicons name="videocam-off-outline" size={32} color="#CBD5E1" />
            <Text style={styles.cameraPausedText}>Cámara en pausa</Text>
          </View>
        )}

        <View pointerEvents="none" style={styles.cameraOverlay}>
          {isRecording ? (
            <View style={styles.recBadge}>
              <View style={styles.recDot} />
              <Text style={styles.recText}>REC · {countdown} s</Text>
            </View>
          ) : isCapturingPhoto ? (
            <View style={styles.statusBadge}>
              <Text style={styles.statusBadgeText}>Capturando foto...</Text>
            </View>
          ) : isUploading ? (
            <View style={styles.statusBadge}>
              <ActivityIndicator size="small" color="#FFFFFF" />
              <Text style={styles.statusBadgeText}>Analizando vehículo...</Text>
            </View>
          ) : (
            <View style={styles.statusBadge}>
              <Text style={styles.statusBadgeText}>720p · Listo para captura</Text>
            </View>
          )}
        </View>
      </View>

      {cameraMountError ? (
        <View style={styles.errorCard}>
          <Text style={styles.errorTitle}>Error de cámara</Text>
          <Text style={styles.errorBody}>{cameraMountError}</Text>
        </View>
      ) : null}

      {/* Botones de captura */}
      <View style={styles.captureRow}>
        <Pressable
          style={({ pressed }) => [
            styles.recordButton,
            controlsDisabled && styles.disabledButton,
            pressed && !controlsDisabled && styles.pressed,
          ]}
          disabled={controlsDisabled}
          onPress={handleRecordClip}>
          <Ionicons
            name={isRecording ? 'radio-button-on' : 'videocam'}
            size={20}
            color="#FFFFFF"
          />
          <Text style={styles.recordButtonText}>
            {isRecording
              ? `Grabando (${countdown} s)`
              : isUploading
                ? 'Enviando...'
                : 'Grabar clip (6 s)'}
          </Text>
        </Pressable>

        <Pressable
          style={({ pressed }) => [
            styles.photoButton,
            controlsDisabled && styles.disabledButton,
            pressed && !controlsDisabled && styles.pressed,
          ]}
          disabled={controlsDisabled}
          onPress={handleTakePhoto}>
          <Ionicons name="camera" size={20} color={Palette.primary} />
          <Text style={styles.photoButtonText}>Foto</Text>
        </Pressable>

        <Pressable
          style={({ pressed }) => [
            styles.photoButton,
            controlsDisabled && styles.disabledButton,
            pressed && !controlsDisabled && styles.pressed,
          ]}
          disabled={controlsDisabled}
          onPress={handlePickFromGallery}>
          <Ionicons name="images-outline" size={20} color={Palette.primary} />
        </Pressable>
      </View>

      {/* Error y acciones de recuperación */}
      {errorMsg ? (
        <View style={styles.errorCard}>
          <View style={styles.errorHeader}>
            <Ionicons name="warning" size={18} color={Palette.dangerText} />
            <Text style={styles.errorTitle}>
              {errorRequiresNew ? 'Nueva captura requerida' : 'No se pudo registrar el paso'}
            </Text>
          </View>
          <Text style={styles.errorBody}>{errorMsg}</Text>

          <View style={styles.errorActions}>
            {!errorRequiresNew && pendingCapture ? (
              <Pressable
                style={[styles.retryButton, isUploading && styles.disabledButton]}
                disabled={isUploading}
                onPress={handleRetryUpload}>
                <Ionicons name="refresh" size={16} color="#FFFFFF" />
                <Text style={styles.retryButtonText}>Reintentar envío</Text>
              </Pressable>
            ) : null}
            <Pressable
              style={[styles.newCaptureButton, isUploading && styles.disabledButton]}
              disabled={isUploading}
              onPress={handleNewCapture}>
              <Text style={styles.newCaptureButtonText}>Nueva captura</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      {/* Resultado del paso */}
      {resultado ? (
        <View style={styles.resultSection}>
          <ResultadoPaso resultado={resultado} />
          <Pressable style={styles.newCaptureFullButton} onPress={handleNewCapture}>
            <Ionicons name="add-circle-outline" size={18} color={Palette.primary} />
            <Text style={styles.newCaptureFullText}>Nueva captura</Text>
          </Pressable>
        </View>
      ) : null}

      {/* Modal selector de Caseta */}
      <Modal
        visible={pickerVisible}
        transparent
        animationType="slide"
        onRequestClose={() => setPickerVisible(false)}>
        <View style={styles.modalBackdrop}>
          <View style={styles.modalSheet}>
            <View style={styles.modalHeader}>
              <Text style={styles.modalTitle}>Seleccionar caseta</Text>
              <Pressable onPress={() => setPickerVisible(false)}>
                <Ionicons name="close" size={24} color={Palette.text} />
              </Pressable>
            </View>

            {casetasError ? (
              <View style={styles.modalEmpty}>
                <Text style={styles.errorBody}>{casetasError}</Text>
                <Pressable style={styles.primaryButton} onPress={reloadCasetas}>
                  <Text style={styles.primaryButtonText}>Reintentar</Text>
                </Pressable>
              </View>
            ) : casetas.length === 0 ? (
              <View style={styles.modalEmpty}>
                <Text style={styles.mutedText}>No hay casetas registradas.</Text>
                <Pressable style={styles.secondaryButton} onPress={reloadCasetas}>
                  <Text style={styles.secondaryButtonText}>Actualizar</Text>
                </Pressable>
              </View>
            ) : (
              <ScrollView style={styles.modalList}>
                {casetas.map((caseta) => {
                  const selected = caseta.id === selectedCasetaId;
                  return (
                    <Pressable
                      key={caseta.id}
                      style={[styles.casetaOption, selected && styles.casetaOptionSelected]}
                      onPress={async () => {
                        await selectCaseta(caseta.id);
                        setPickerVisible(false);
                      }}>
                      <View style={styles.casetaOptionText}>
                        <Text style={styles.casetaOptionName}>{caseta.nombre}</Text>
                        <Text style={styles.casetaOptionLoc}>{caseta.ubicacion}</Text>
                      </View>
                      {selected ? (
                        <Ionicons name="checkmark-circle" size={22} color={Palette.primary} />
                      ) : null}
                    </Pressable>
                  );
                })}
              </ScrollView>
            )}
          </View>
        </View>
      </Modal>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  screen: {
    flex: 1,
    backgroundColor: Palette.background,
  },
  content: {
    padding: 16,
    gap: 14,
    paddingBottom: 28,
  },
  centered: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
    backgroundColor: Palette.background,
    gap: 12,
  },
  mutedText: {
    fontSize: 14,
    color: Palette.textSecondary,
    textAlign: 'center',
  },
  permissionCard: {
    width: '100%',
    backgroundColor: Palette.surface,
    borderRadius: 18,
    borderWidth: 1,
    borderColor: Palette.border,
    padding: 24,
    alignItems: 'center',
    gap: 12,
  },
  permissionTitle: {
    fontSize: 19,
    fontWeight: '700',
    color: Palette.text,
    textAlign: 'center',
  },
  permissionBody: {
    fontSize: 14,
    color: Palette.textSecondary,
    textAlign: 'center',
    lineHeight: 20,
  },
  casetaBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: Palette.surface,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: Palette.border,
    paddingHorizontal: 14,
    paddingVertical: 12,
    gap: 10,
  },
  casetaInfo: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  casetaTextWrap: {
    flex: 1,
  },
  casetaLabel: {
    fontSize: 11,
    fontWeight: '600',
    color: Palette.textMuted,
    textTransform: 'uppercase',
  },
  casetaName: {
    fontSize: 15,
    fontWeight: '700',
    color: Palette.text,
  },
  casetaError: {
    fontSize: 14,
    fontWeight: '600',
    color: Palette.dangerText,
  },
  casetaRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
  },
  casetaAction: {
    fontSize: 13,
    fontWeight: '700',
    color: Palette.primary,
  },
  cameraFrame: {
    width: '100%',
    aspectRatio: 4 / 3,
    borderRadius: 18,
    overflow: 'hidden',
    backgroundColor: '#0F172A',
    position: 'relative',
  },
  camera: {
    flex: 1,
  },
  cameraPaused: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    gap: 8,
  },
  cameraPausedText: {
    color: '#CBD5E1',
    fontSize: 14,
    fontWeight: '600',
  },
  cameraOverlay: {
    position: 'absolute',
    top: 12,
    left: 12,
    right: 12,
    flexDirection: 'row',
    justifyContent: 'space-between',
  },
  recBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: 'rgba(220, 38, 38, 0.92)',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 999,
  },
  recDot: {
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: '#FFFFFF',
  },
  recText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '800',
  },
  statusBadge: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: 'rgba(15, 23, 42, 0.72)',
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 999,
  },
  statusBadgeText: {
    color: '#FFFFFF',
    fontSize: 12,
    fontWeight: '600',
  },
  captureRow: {
    flexDirection: 'row',
    gap: 10,
  },
  recordButton: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: Palette.primary,
    paddingVertical: 15,
    borderRadius: 14,
  },
  recordButtonText: {
    color: '#FFFFFF',
    fontSize: 16,
    fontWeight: '700',
  },
  photoButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: Palette.surface,
    borderWidth: 1.5,
    borderColor: Palette.primary,
    paddingHorizontal: 18,
    paddingVertical: 15,
    borderRadius: 14,
  },
  photoButtonText: {
    color: Palette.primary,
    fontSize: 15,
    fontWeight: '700',
  },
  disabledButton: {
    opacity: 0.5,
  },
  pressed: {
    opacity: 0.85,
  },
  errorCard: {
    backgroundColor: Palette.dangerBg,
    borderRadius: 14,
    padding: 14,
    gap: 8,
  },
  errorHeader: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
  },
  errorTitle: {
    fontSize: 14,
    fontWeight: '700',
    color: Palette.dangerText,
  },
  errorBody: {
    fontSize: 14,
    color: Palette.dangerText,
    lineHeight: 20,
  },
  errorActions: {
    flexDirection: 'row',
    gap: 10,
    marginTop: 4,
  },
  retryButton: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    backgroundColor: Palette.danger,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 10,
  },
  retryButtonText: {
    color: '#FFFFFF',
    fontSize: 13,
    fontWeight: '700',
  },
  newCaptureButton: {
    backgroundColor: Palette.surface,
    borderWidth: 1,
    borderColor: Palette.border,
    paddingHorizontal: 14,
    paddingVertical: 10,
    borderRadius: 10,
  },
  newCaptureButtonText: {
    color: Palette.text,
    fontSize: 13,
    fontWeight: '700',
  },
  resultSection: {
    gap: 10,
  },
  newCaptureFullButton: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: Palette.primaryLight,
    paddingVertical: 13,
    borderRadius: 12,
  },
  newCaptureFullText: {
    color: Palette.primary,
    fontSize: 15,
    fontWeight: '700',
  },
  primaryButton: {
    backgroundColor: Palette.primary,
    paddingHorizontal: 20,
    paddingVertical: 13,
    borderRadius: 12,
  },
  primaryButtonText: {
    color: '#FFFFFF',
    fontSize: 15,
    fontWeight: '700',
  },
  secondaryButton: {
    backgroundColor: Palette.surfaceMuted,
    paddingHorizontal: 18,
    paddingVertical: 12,
    borderRadius: 12,
  },
  secondaryButtonText: {
    color: Palette.text,
    fontSize: 14,
    fontWeight: '600',
  },
  modalBackdrop: {
    flex: 1,
    backgroundColor: 'rgba(15, 23, 42, 0.45)',
    justifyContent: 'flex-end',
  },
  modalSheet: {
    backgroundColor: Palette.surface,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: 20,
    maxHeight: '70%',
    gap: 14,
  },
  modalHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: Palette.text,
  },
  modalList: {
    maxHeight: 340,
  },
  modalEmpty: {
    alignItems: 'center',
    paddingVertical: 20,
    gap: 12,
  },
  casetaOption: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: 14,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: Palette.border,
    marginBottom: 8,
  },
  casetaOptionSelected: {
    borderColor: Palette.primary,
    backgroundColor: Palette.primaryLight,
  },
  casetaOptionText: {
    flex: 1,
    gap: 2,
  },
  casetaOptionName: {
    fontSize: 15,
    fontWeight: '700',
    color: Palette.text,
  },
  casetaOptionLoc: {
    fontSize: 13,
    color: Palette.textSecondary,
  },
});
