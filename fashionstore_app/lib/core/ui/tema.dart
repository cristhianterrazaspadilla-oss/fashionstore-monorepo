import 'package:flutter/material.dart';

import 'colores.dart';

/// Identidad visual FashionStore unificada con los design tokens web.
///
/// - Botones principales oscuros ([ColoresFS.ink]) con texto blanco.
/// - Latón ([ColoresFS.brass]) solo para selección, indicadores y detalles.
/// - Patrones nativos móviles: NavigationBar inferior, AppBar compacta,
///   ModalBottomSheet para filtros, diálogos y selectores accesibles.
/// - Áreas táctiles mínimas de 44–48 px, sin overflow en 320 px.
ThemeData temaFashionStore() {
  final esquema = ColorScheme.fromSeed(
    seedColor: ColoresFS.ink,
    primary: ColoresFS.ink,
    onPrimary: Colors.white,
    secondary: ColoresFS.brass,
    onSecondary: Colors.white,
    surface: ColoresFS.surface,
    onSurface: ColoresFS.ink,
    error: ColoresFS.danger,
    onError: Colors.white,
  );
  return ThemeData(
    colorScheme: esquema,
    useMaterial3: true,
    scaffoldBackgroundColor: ColoresFS.canvas,
    splashFactory: InkSparkle.splashFactory,
    appBarTheme: const AppBarTheme(
      centerTitle: false,
      backgroundColor: ColoresFS.surface,
      foregroundColor: ColoresFS.ink,
      elevation: 0,
      scrolledUnderElevation: 1,
      toolbarHeight: 56,
      titleTextStyle: TextStyle(
        color: ColoresFS.ink,
        fontSize: 19,
        fontWeight: FontWeight.w800,
      ),
    ),
    textTheme: const TextTheme(
      bodyLarge: TextStyle(color: ColoresFS.textBody),
      bodyMedium: TextStyle(color: ColoresFS.textBody),
      bodySmall: TextStyle(color: ColoresFS.textMuted),
      titleLarge: TextStyle(color: ColoresFS.ink, fontWeight: FontWeight.w800),
      titleMedium: TextStyle(color: ColoresFS.ink, fontWeight: FontWeight.w700),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: ColoresFS.surface,
      hintStyle: const TextStyle(color: ColoresFS.textMuted),
      labelStyle: const TextStyle(color: ColoresFS.textMuted),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(ColoresFS.radioControl),
        borderSide: const BorderSide(color: ColoresFS.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(ColoresFS.radioControl),
        borderSide: const BorderSide(color: ColoresFS.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(ColoresFS.radioControl),
        borderSide: const BorderSide(color: ColoresFS.brassStrong, width: 1.6),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(ColoresFS.radioControl),
        borderSide: const BorderSide(color: ColoresFS.danger),
      ),
      contentPadding: const EdgeInsets.symmetric(horizontal: 14, vertical: 14),
    ),
    elevatedButtonTheme: ElevatedButtonThemeData(
      style: ElevatedButton.styleFrom(
        backgroundColor: ColoresFS.ink,
        foregroundColor: Colors.white,
        minimumSize: const Size(48, 48),
        textStyle: const TextStyle(fontSize: 15, fontWeight: FontWeight.w700),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(ColoresFS.radioControl),
        ),
      ),
    ),
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        foregroundColor: ColoresFS.ink,
        minimumSize: const Size(48, 44),
        side: const BorderSide(color: ColoresFS.border),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(ColoresFS.radioControl),
        ),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: ColoresFS.inkSoft,
        minimumSize: const Size(48, 44),
      ),
    ),
    cardTheme: CardThemeData(
      elevation: 0,
      color: ColoresFS.surface,
      margin: const EdgeInsets.symmetric(vertical: 5),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(ColoresFS.radioTarjeta),
        side: const BorderSide(color: ColoresFS.border),
      ),
    ),
    chipTheme: ChipThemeData(
      selectedColor: ColoresFS.brassSoft,
      checkmarkColor: ColoresFS.brassStrong,
      labelStyle: const TextStyle(color: ColoresFS.ink),
      secondaryLabelStyle: const TextStyle(color: ColoresFS.brassStrong),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(999),
        side: const BorderSide(color: ColoresFS.border),
      ),
    ),
    checkboxTheme: CheckboxThemeData(
      fillColor: WidgetStateProperty.resolveWith((estados) {
        if (estados.contains(WidgetState.selected)) {
          return ColoresFS.brassStrong;
        }
        return null;
      }),
    ),
    radioTheme: RadioThemeData(
      fillColor: WidgetStateProperty.resolveWith((estados) {
        if (estados.contains(WidgetState.selected)) {
          return ColoresFS.brassStrong;
        }
        return null;
      }),
    ),
    switchTheme: SwitchThemeData(
      thumbColor: WidgetStateProperty.resolveWith((estados) {
        if (estados.contains(WidgetState.selected)) {
          return ColoresFS.brassStrong;
        }
        return null;
      }),
      trackColor: WidgetStateProperty.resolveWith((estados) {
        if (estados.contains(WidgetState.selected)) {
          return ColoresFS.brassSoft;
        }
        return null;
      }),
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: ColoresFS.brassStrong,
    ),
    navigationBarTheme: NavigationBarThemeData(
      backgroundColor: ColoresFS.surface,
      indicatorColor: ColoresFS.brassSoft,
      iconTheme: WidgetStateProperty.resolveWith((estados) {
        if (estados.contains(WidgetState.selected)) {
          return const IconThemeData(color: ColoresFS.brassStrong);
        }
        return const IconThemeData(color: ColoresFS.textMuted);
      }),
      labelTextStyle: WidgetStateProperty.resolveWith((estados) {
        if (estados.contains(WidgetState.selected)) {
          return const TextStyle(
            color: ColoresFS.brassStrong,
            fontWeight: FontWeight.w700,
            fontSize: 12,
          );
        }
        return const TextStyle(color: ColoresFS.textMuted, fontSize: 12);
      }),
    ),
    snackBarTheme: SnackBarThemeData(
      behavior: SnackBarBehavior.floating,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(ColoresFS.radioControl),
      ),
    ),
    dialogTheme: DialogThemeData(
      backgroundColor: ColoresFS.surface,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(ColoresFS.radioTarjeta),
      ),
    ),
    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: ColoresFS.surface,
      showDragHandle: true,
    ),
  );
}
