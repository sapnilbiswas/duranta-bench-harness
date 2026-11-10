CC ?= gcc
CFLAGS ?= -O2 -Wall -Wextra
DURANTA_PATH ?= /workspace/openairinterface5g

INCLUDES = -I$(DURANTA_PATH)/common/utils
LDFLAGS = -lm -lpthread

TARGET = meas_overhead
SRC = meas_overhead.c

all: $(TARGET)

$(TARGET): $(SRC)
	$(CC) $(CFLAGS) $(INCLUDES) $(SRC) -o $(TARGET) $(LDFLAGS)

clean:
	rm -f $(TARGET)

.PHONY: all clean
