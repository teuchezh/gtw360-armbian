#include <fcntl.h>
#include <linux/watchdog.h>
#include <sys/ioctl.h>
#include <unistd.h>

int main(void)
{
    int fd = open("/dev/watchdog", O_WRONLY | O_CLOEXEC);
    int timeout = 60;
    if (fd < 0)
        return 1;
    if (ioctl(fd, WDIOC_SETTIMEOUT, &timeout) < 0)
        return 2;
    for (;;) {
        if (ioctl(fd, WDIOC_KEEPALIVE, 0) < 0)
            return 3;
        sleep(5);
    }
}
