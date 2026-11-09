import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { AuthService } from '../../features/identidad_empresas/services/auth.service';

export const authGuard: CanActivateFn = (route, state) => {
  const authService = inject(AuthService);
  const router = inject(Router);

  if (!authService.estaAutenticado()) {
    return router.createUrlTree(['/auth/login'], { queryParams: { redirectUrl: state.url } });
  }

  // Validar ventana de privacidad de 8 horas
  if (!authService.esVentanaPrivacidadValida()) {
    authService.cerrarSesion();
    return router.createUrlTree(['/auth/login'], {
      queryParams: { redirectUrl: state.url, expirado: '1' }
    });
  }

  // Si la ruta define roles permitidos en data: { roles: ['ADMINISTRADOR', ...] }
  const rolesPermitidos = route.data?.['roles'] as Array<string> | undefined;
  if (rolesPermitidos && rolesPermitidos.length > 0) {
    const usuario = authService.obtenerUsuarioActual();
    if (!usuario || !rolesPermitidos.includes(usuario.rol)) {
      return router.createUrlTree(['/'], { queryParams: { denegado: '1' } });
    }
  }

  return true;
};

export const platformHomeGuard: CanActivateFn = () => {
  const auth = inject(AuthService);
  const usuario = auth.obtenerUsuarioActual();
  if (usuario && !usuario.empresa_id && ['SUPERADMIN', 'ADMINISTRADOR_PLATAFORMA', 'ADMINISTRADOR_SISTEMA'].includes(usuario.rol)) {
    return inject(Router).createUrlTree(['/plataforma']);
  }
  return true;
};
