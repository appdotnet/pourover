(function () {
  'use strict';

  angular.module('pourOver').controller('ChannelCtrl', function (ApiClient, Channels, Auth, $scope, $rootScope, $routeParams, $location) {
    $scope.messages = [];
    $scope.message = {};
    $scope.channelMetadata = {title: '', description: ''};

    $scope.currentChannelId = $routeParams.channel_id;
    $scope.currentChannel = _.find($rootScope.channels, function (channel) {
      return channel.id === $scope.currentChannelId;
    });

    $scope.redirect_uri = window.location.origin + $location.path();
    if (!Auth.isLoggedIn()) {
      Auth.login();
    }
    if (! $scope.currentChannel) {
      ApiClient.getChannel($scope.currentChannelId, {
        params: {
          include_annotations: 1
        }
      }).success(function (data) {
        var channel = data.data;
        if (channel.type === 'net.app.core.broadcast') {
          $scope.currentChannel = channel;
        }
      }).error(function (data, status) {
        if (status === 401 || status === 403) {
          $rootScope.local.nextUrlPath = $location.path();
          $location.path('/login');
        }
      });
    }

    var escapeHtml = function (rawHtml) {
      return jQuery('<div/>').text(rawHtml).html();
    };

    var Message = function (data) {
      angular.extend(this, data);
    };

    var fit_to_box = function (w, h, max_w, max_h, expand) {
      expand = expand || false;
      // proportionately scale a box defined by (w,h) so that it fits within a box defined by (max_w, max_h)
      // by default, only scaling down is allowed, unless expand=True, in which case scaling up is allowed
      if ((w < max_w) && (h < max_h) && !expand) {
        return [w, h];
      }
      var largest_ratio = Math.max(w / max_w, h / max_h);
      var new_height = parseInt(h / largest_ratio, 10);
      var new_width = parseInt(w / largest_ratio, 10);
      return [new_width, new_height];
    };

    Message.prototype.oembed = function () {
      var embed = _.find(this.annotations || [], function (annotation) {
        return annotation.type === 'net.app.core.oembed' && annotation.value;
      });
      var dimensions = {}
      if (embed && embed.value.thumbnail_url) {
        dimensions = fit_to_box(embed.value.thumbnail_width, embed.value.thumbnail_height, 100, 100);
        dimensions = {
          'thumbnail_width': dimensions[0],
          'thumbnail_height': dimensions[1]
        };
      }
      return embed && angular.extend(embed.value, dimensions);
    };

    $scope.$watch('currentChannel', function () {
      if ($scope.currentChannel) {
        var metadata = ApiClient.getChannelMetadata($scope.currentChannel);
        $scope.channelMetadata.title = metadata.title;
        $scope.channelMetadata.description = escapeHtml(metadata.description);

        ApiClient.getMessages($scope.currentChannel, true).success(function (data) {
          $scope.messages = _.map(data.data, function (data) {
            return new Message(data);
          });
        });
      }
    });

    $scope.unsubscribeFrom = function (channel) {
      ApiClient.unsubscribeFromChannel(channel, {
        params: {
          include_annotations: 1
        }
      }).success(function (data) {
        $scope.currentChannel = data.data;
      });
    };

    $scope.subscribeTo = function (channel) {
      ApiClient.subscribeToChannel(channel, {
        params: {
          include_annotations: 1
        }
      }).success(function (data) {
        $scope.currentChannel = data.data;
      });
    };

    $scope.sendText = function () {
      ApiClient.createMessage($scope.currentChannel, $scope.message.processedMessage).success(function (data) {
        $scope.messages.unshift(data.data);
        $scope.message.rawText = '';
      });
    };

  });

  angular.module('pourOver').directive('channelAcl', function () {
    return {
      restrict: 'A',
      templateUrl: '/views/channel-acl.html',
      replace: true,
      link: function (scope) {
        scope.$watch('users', function (newValue) {
          scope.acl.user_ids = _.map(newValue, function (user) {
            return user.id;
          });
        });
      },
      scope: {
        acl: '=',
        allowPublic: '@',
        allowAnyUser: '@',
        allowUserIds: '@',
        label: '@'
      }
    };
  });

  angular.module('pourOver').controller('NewChannelCtrl', function (ApiClient, $scope) {
    $scope.readers = {
      any_user: true,
      public: true,
      user_ids: []
    };
    $scope.writers = {
      any_user: false,
      public: false,
      user_ids: []
    };

    $scope.create = function () {
      var channel = {
        type: 'net.app.core.broadcast',
        readers: $scope.readers,
        writers: $scope.writers
      };
      var annotations = [{
        type: 'net.app.core.broadcast.metadata',
        value: {
          title: $scope.title,
          description: $scope.description
        }
      }];

      ApiClient.createChannel(channel).success(function (data) {
        var channel = data.data;
        var full_url = window.location.origin + "/channels/" + channel.id + '/';

        annotations[0].value.fallback_url = full_url;
        ApiClient.updateChannel(channel, {annotations: annotations}).success(function () {
          ApiClient.subscribeToChannel(channel).success(function () {
            window.location = full_url;
          });
        });
      });
    };
  });
}());
