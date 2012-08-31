$(function () {
	$('#askpass').submit(function() {
		postdata = {password: $('#password').val(), testsuite: $('#testsuite').val()};
		$.post('auth', postdata, function(data) {
			if (data == 'Password OK') {
				window.location.href = '/testsuites'
			} else {
				$('.error-message').html(data)
				$('.error').show()
				$('#password').val('')
			}
        });
		return false;
	});
});
