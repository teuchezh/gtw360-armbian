#include <fcntl.h>
#include <linux/fs.h>
#include <stdio.h>
#include <sys/ioctl.h>
#include <unistd.h>

int main(int argc, char **argv)
{
    if (argc != 2) {
        fprintf(stderr, "Usage: %s BLOCK_DEVICE\n", argv[0]);
        return 2;
    }
    int fd = open(argv[1], O_RDONLY | O_CLOEXEC);
    if (fd < 0) {
        perror("open");
        return 1;
    }
    if (ioctl(fd, BLKRRPART) < 0) {
        perror("BLKRRPART");
        close(fd);
        return 1;
    }
    close(fd);
    return 0;
}
