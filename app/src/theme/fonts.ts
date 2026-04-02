/**
 * fonts.ts — Tipografia del sistema Multitel Reportes
  */
  import { Platform } from 'react-native';

  export const FONTS = {
    regular: Platform.select({
        android: 'Roboto',
            ios: 'System',
                default: 'System',
                  }) ?? 'System',
                    medium: Platform.select({
                        android: 'Roboto-Medium',
                            ios: 'System',
                                default: 'System',
                                  }) ?? 'System',
                                    semibold: Platform.select({
                                        android: 'Roboto-Medium',
                                            ios: 'System',
                                                default: 'System',
                                                  }) ?? 'System',
                                                    bold: Platform.select({
                                                        android: 'Roboto-Bold',
                                                            ios: 'System',
                                                                default: 'System',
                                                                  }) ?? 'System',
                                                                    mono: Platform.select({
                                                                        android: 'monospace',
                                                                            ios: 'Courier',
                                                                                default: 'monospace',
                                                                                  }) ?? 'monospace',
                                                                                  } as const;

                                                                                  export const FONT_SIZES = {
                                                                                    xs: 11,
                                                                                      sm: 13,
                                                                                        base: 15,
                                                                                          md: 16,
                                                                                            lg: 18,
                                                                                              xl: 20,
                                                                                                xxl: 24,
                                                                                                  h1: 28,
                                                                                                    h2: 22,
                                                                                                      h3: 18,
                                                                                                      } as const;
                                                                                                      
                                                                                                      export const LINE_HEIGHTS = {
                                                                                                        tight: 1.25,
                                                                                                          normal: 1.5,
                                                                                                            relaxed: 1.75,
                                                                                                            } as const;
