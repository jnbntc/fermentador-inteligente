#include <assert.h>
#include <stdint.h>
#include "cooling_guard.h"

int main() {
    CoolingGuard guard(300000);
    guard.reset(100);
    assert(!guard.requestOn(300099));
    assert(guard.requestOn(300100));

    // Un sensor desconectado tras mucho tiempo encendido debe iniciar otra espera.
    guard.forceOff(900000);
    assert(!guard.requestOn(900001));
    assert(!guard.requestOn(1199999));
    assert(guard.requestOn(1200000));

    // Apagados repetidos no reinician indefinidamente el intervalo.
    guard.forceOff(1200010);
    guard.forceOff(1200020);
    assert(guard.requestOn(1500010));

    // Un reinicio debe bloquear aunque el compresor estuviera funcionando.
    guard.reset(0);
    assert(!guard.requestOn(0));
    assert(!guard.requestOn(299999));
    assert(guard.requestOn(300000));

    // millis() vuelve a cero: la resta unsigned debe conservar el tiempo transcurrido.
    guard.reset(UINT32_MAX - 100000);
    assert(!guard.requestOn(199998));
    assert(guard.requestOn(199999));
}
